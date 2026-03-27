import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { TelemetryPayload, PLAN_LIMITS } from "@humphi/types";
import { apiCalls, users } from "@humphi/db";
import { eq } from "drizzle-orm";
import { db } from "../../lib/db";
import {
  incrementDailyUsage,
  getPlanFromCache,
  setPlanCache,
  checkRateLimit,
} from "../../lib/redis";
import { inngest } from "../../lib/inngest";
import { requireAuth } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const telemetryRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

telemetryRoutes.post(
  "/",
  requireAuth,
  zValidator("json", TelemetryPayload),
  async (c) => {
    const userId = c.get("userId");
    const body = c.req.valid("json");

    // Rate limit: max 5 telemetry posts per second per user
    const { allowed } = await checkRateLimit(c.env, `tel:${userId}`, 5, 1);
    if (!allowed) return c.json({ ok: true }); // silently drop duplicates

    // Get plan limit (Redis cache → DB fallback)
    let plan = await getPlanFromCache(c.env, userId);
    if (!plan) {
      const [user] = await db(c.env).select({ plan: users.plan }).from(users).where(eq(users.id, userId)).limit(1);
      plan = user?.plan ?? "free";
      await setPlanCache(c.env, userId, plan);
    }
    const limit = PLAN_LIMITS[plan as keyof typeof PLAN_LIMITS].dailyCalls;

    // Increment daily counter
    const usage = await incrementDailyUsage(c.env, userId);

    // Hard limit check
    if (usage > limit) {
      return c.json({ error: "Daily limit exceeded. Please upgrade your plan." }, 429);
    }

    // Insert API call record
    await db(c.env).insert(apiCalls).values({
      userId,
      sessionId: body.sessionId,
      model: body.model,
      intent: body.intent,
      promptTokens: body.promptTokens,
      completionTokens: body.completionTokens,
      totalTokens: body.totalTokens,
      costUsd: String(body.costUsd),
      latencyMs: body.latencyMs,
      wasCacheHit: body.wasCacheHit,
      capabilityUsed: body.capabilityUsed,
      mcpToolsCalled: JSON.stringify(body.mcpToolsCalled),
    });

    // Trigger usage alert via Inngest (event-driven, not cron)
    if (limit !== Infinity) {
      const pct = usage / limit;
      if (pct >= 0.8 && pct < 0.81) {
        await inngest.send({ name: "usage/alert", data: { userId, usage, limit, threshold: 80 } });
      } else if (usage >= limit) {
        await inngest.send({ name: "usage/alert", data: { userId, usage, limit, threshold: 100 } });
      }
    }

    return c.json({ ok: true, usage, limit });
  }
);
