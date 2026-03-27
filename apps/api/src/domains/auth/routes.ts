import { Hono } from "hono";
import { users } from "@humphi/db";
import { db } from "../../lib/db";
import { sendEmail, EMAIL_TEMPLATES } from "../../lib/brevo";
import type { Env, Variables } from "../../types";

export const authRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// POST /auth/clerk-webhook — Clerk fires this on user.created
authRoutes.post("/clerk-webhook", async (c) => {
  const payload = await c.req.json();
  const { type, data } = payload;

  if (type === "user.created") {
    const email = data.email_addresses?.[0]?.email_address;
    const name = [data.first_name, data.last_name].filter(Boolean).join(" ") || null;

    await db(c.env)
      .insert(users)
      .values({ id: data.id, email, name, plan: "free", role: "user" })
      .onConflictDoNothing();

    // Send welcome email
    if (email) {
      await sendEmail(
        c.env,
        { email, name: name ?? email },
        EMAIL_TEMPLATES.WELCOME,
        { name: name ?? "there" }
      );
    }
  }

  return c.json({ ok: true });
});
