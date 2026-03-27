import { Hono } from "hono";
import { eq } from "drizzle-orm";
import { users, preferences } from "@humphi/db";
import { db } from "../../lib/db";
import { requireAuth } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const userRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// GET /users/me
userRoutes.get("/me", requireAuth, async (c) => {
  const userId = c.get("userId");
  const [user] = await db(c.env).select().from(users).where(eq(users.id, userId)).limit(1);
  if (!user) return c.json({ error: "User not found" }, 404);
  return c.json({ user });
});

// GET /users/me/preferences
userRoutes.get("/me/preferences", requireAuth, async (c) => {
  const userId = c.get("userId");
  const [prefs] = await db(c.env).select().from(preferences).where(eq(preferences.userId, userId)).limit(1);
  return c.json({ preferences: prefs ?? null });
});

// PATCH /users/me/preferences
userRoutes.patch("/me/preferences", requireAuth, async (c) => {
  const userId = c.get("userId");
  const body = await c.req.json();

  await db(c.env)
    .insert(preferences)
    .values({ userId, ...body })
    .onConflictDoUpdate({
      target: preferences.userId,
      set: { ...body, updatedAt: new Date() },
    });

  return c.json({ ok: true });
});
