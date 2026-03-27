import { Hono } from "hono";
import { count, sum, gte, isNull, ilike, eq, or, and } from "drizzle-orm";
import { users, sessions, apiCalls } from "@humphi/db";
import { db } from "../../lib/db";
import { requireAuth, requireAdmin } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const adminRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

function rangeToDate(range: string): Date {
  const now = new Date();
  switch (range) {
    case "today": return new Date(now.toISOString().split("T")[0]);
    case "7d":    return new Date(Date.now() - 7 * 86400000);
    case "30d":   return new Date(Date.now() - 30 * 86400000);
    default:      return new Date(0);
  }
}

// GET /admin/stats?range=today|7d|30d|all
adminRoutes.get("/stats", requireAuth, requireAdmin, async (c) => {
  const range = c.req.query("range") ?? "today";
  const from = rangeToDate(range);

  const [userCount, callData, activeSessions] = await Promise.all([
    db(c.env).select({ count: count() }).from(users),
    db(c.env)
      .select({ callCount: count(), totalCost: sum(apiCalls.costUsd) })
      .from(apiCalls)
      .where(gte(apiCalls.timestamp, from)),
    db(c.env).select({ count: count() }).from(sessions).where(isNull(sessions.endedAt)),
  ]);

  return c.json({
    totalUsers: userCount[0].count,
    totalCalls: callData[0].callCount,
    totalCostUsd: callData[0].totalCost ?? "0",
    activeSessions: activeSessions[0].count,
  });
});

// GET /admin/users?search=&plan=&page=
adminRoutes.get("/users", requireAuth, requireAdmin, async (c) => {
  const { search, plan, page = "1" } = c.req.query();
  const conditions = [];
  if (search) conditions.push(or(ilike(users.email, `%${search}%`), ilike(users.name as any, `%${search}%`)));
  if (plan)   conditions.push(eq(users.plan, plan));

  const rows = await db(c.env)
    .select()
    .from(users)
    .where(conditions.length ? and(...conditions) : undefined)
    .limit(20)
    .offset((Number(page) - 1) * 20);

  return c.json({ users: rows });
});

// GET /admin/users/:id
adminRoutes.get("/users/:id", requireAuth, requireAdmin, async (c) => {
  const userId = c.req.param("id");

  const [user, userSessions, calls] = await Promise.all([
    db(c.env).select().from(users).where(eq(users.id, userId)).limit(1),
    db(c.env).select().from(sessions).where(eq(sessions.userId, userId)).limit(20),
    db(c.env).select().from(apiCalls).where(eq(apiCalls.userId, userId)).limit(50),
  ]);

  if (!user[0]) return c.json({ error: "Not found" }, 404);
  return c.json({ user: user[0], sessions: userSessions, calls });
});
