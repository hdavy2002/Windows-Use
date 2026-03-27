import { Hono } from "hono";
import { eq, desc, and, isNull } from "drizzle-orm";
import { sessions } from "@humphi/db";
import { zValidator } from "@hono/zod-validator";
import { SessionStartPayload, SessionEndPayload } from "@humphi/types";
import { db } from "../../lib/db";
import { redis } from "../../lib/redis";
import { requireAuth } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const sessionRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// POST /sessions/start
sessionRoutes.post("/start", requireAuth, zValidator("json", SessionStartPayload), async (c) => {
  const userId = c.get("userId");
  const { mode, source } = c.req.valid("json");

  const [session] = await db(c.env)
    .insert(sessions)
    .values({ userId, mode, source })
    .returning();

  // Cache session → userId mapping for 2 hours
  await redis(c.env).set(`session:${session.id}`, userId, { ex: 7200 });

  return c.json({ sessionId: session.id });
});

// PATCH /sessions/:id/end
sessionRoutes.patch("/:id/end", requireAuth, zValidator("json", SessionEndPayload), async (c) => {
  const sessionId = c.req.param("id");
  const { summary } = c.req.valid("json");

  await db(c.env)
    .update(sessions)
    .set({ endedAt: new Date(), summary })
    .where(eq(sessions.id, sessionId));

  await redis(c.env).del(`session:${sessionId}`);
  return c.json({ ok: true });
});

// GET /sessions — paginated list for current user
sessionRoutes.get("/", requireAuth, async (c) => {
  const userId = c.get("userId");
  const page = Number(c.req.query("page") ?? 1);

  const rows = await db(c.env)
    .select()
    .from(sessions)
    .where(eq(sessions.userId, userId))
    .orderBy(desc(sessions.startedAt))
    .limit(20)
    .offset((page - 1) * 20);

  return c.json({ sessions: rows });
});
