import { createMiddleware } from "hono/factory";
import { verifyToken } from "@clerk/backend";
import type { Env, Variables } from "../../types";

export const requireAuth = createMiddleware<{
  Bindings: Env;
  Variables: Variables;
}>(async (c, next) => {
  const authHeader = c.req.header("Authorization");
  const token = authHeader?.replace("Bearer ", "");

  if (!token) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  try {
    const payload = await verifyToken(token, {
      secretKey: c.env.CLERK_SECRET_KEY,
    });
    c.set("userId", payload.sub);
    await next();
  } catch {
    return c.json({ error: "Invalid token" }, 401);
  }
});

export const requireAdmin = createMiddleware<{
  Bindings: Env;
  Variables: Variables;
}>(async (c, next) => {
  const userId = c.get("userId");
  const { db } = await import("../../lib/db");
  const { users } = await import("@humphi/db");
  const { eq } = await import("drizzle-orm");

  const [user] = await db(c.env).select().from(users).where(eq(users.id, userId)).limit(1);
  if (user?.role !== "admin") {
    return c.json({ error: "Forbidden" }, 403);
  }
  await next();
});
