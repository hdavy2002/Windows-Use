import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { eq } from "drizzle-orm";
import { users } from "@humphi/db";
import { CheckoutPayload } from "@humphi/types";
import { db } from "../../lib/db";
import { stripe } from "../../lib/stripe";
import { bustPlanCache } from "../../lib/redis";
import { sendEmail, EMAIL_TEMPLATES } from "../../lib/brevo";
import { requireAuth } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const billingRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// ── POST /billing/checkout ────────────────────────────────────────────────────
// Creates a Stripe Checkout session and returns the hosted URL.
billingRoutes.post("/checkout", requireAuth, zValidator("json", CheckoutPayload), async (c) => {
  const userId = c.get("userId");
  const { plan } = c.req.valid("json");

  const [user] = await db(c.env)
    .select()
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  if (!user) return c.json({ error: "User not found" }, 404);

  const priceId = plan === "pro" ? c.env.STRIPE_PRICE_PRO : c.env.STRIPE_PRICE_CORPORATE;

  const session = await stripe(c.env).checkout.sessions.create({
    mode: "subscription",
    customer: user.stripeCustomerId ?? undefined,
    customer_email: user.stripeCustomerId ? undefined : user.email,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: `${c.env.WEB_URL}/dashboard/billing?success=1`,
    cancel_url: `${c.env.WEB_URL}/dashboard/billing?cancelled=1`,
    metadata: { userId, plan },
    subscription_data: {
      metadata: { userId, plan },
    },
  });

  return c.json({ url: session.url });
});

// ── POST /billing/portal ──────────────────────────────────────────────────────
// Returns a Stripe Customer Portal URL so users can manage their subscription.
billingRoutes.post("/portal", requireAuth, async (c) => {
  const userId = c.get("userId");

  const [user] = await db(c.env)
    .select({ stripeCustomerId: users.stripeCustomerId })
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  if (!user?.stripeCustomerId) {
    return c.json({ error: "No billing account found. Subscribe to a plan first." }, 400);
  }

  const session = await stripe(c.env).billingPortal.sessions.create({
    customer: user.stripeCustomerId,
    return_url: `${c.env.WEB_URL}/dashboard/billing`,
  });

  return c.json({ url: session.url });
});

// ── POST /billing/webhook ─────────────────────────────────────────────────────
// Stripe webhook — verifies signature, handles subscription lifecycle events.
// Must be registered WITHOUT requireAuth (Stripe calls this, not users).
billingRoutes.post("/webhook", async (c) => {
  const sig = c.req.header("stripe-signature");
  if (!sig) return c.json({ error: "Missing signature" }, 400);

  // Read raw body — required for signature verification
  const rawBody = await c.req.text();

  let event;
  try {
    event = await stripe(c.env).webhooks.constructEventAsync(
      rawBody,
      sig,
      c.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err: any) {
    console.error("Stripe webhook signature mismatch:", err.message);
    return c.json({ error: "Webhook signature invalid" }, 400);
  }

  const stripeDb = db(c.env);

  switch (event.type) {
    // ── Checkout completed → provision subscription ──────────────────────────
    case "checkout.session.completed": {
      const session = event.data.object as any;
      const userId = session.metadata?.userId;
      const plan = session.metadata?.plan;

      if (!userId || !plan) break;

      await stripeDb
        .update(users)
        .set({
          plan,
          stripeCustomerId: session.customer,
          stripeSubscriptionId: session.subscription,
        })
        .where(eq(users.id, userId));

      await bustPlanCache(c.env, userId);

      // Send upgrade confirmation email
      const [user] = await stripeDb
        .select({ email: users.email, name: users.name })
        .from(users)
        .where(eq(users.id, userId))
        .limit(1);

      if (user) {
        await sendEmail(
          c.env,
          { email: user.email, name: user.name ?? user.email },
          EMAIL_TEMPLATES.PLAN_UPGRADED,
          { plan, userId }
        );
      }
      break;
    }

    // ── Subscription updated → sync plan if tier changed ─────────────────────
    case "customer.subscription.updated": {
      const sub = event.data.object as any;
      const userId = sub.metadata?.userId;
      const plan = sub.metadata?.plan;

      if (!userId || !plan) break;

      await stripeDb
        .update(users)
        .set({ plan, stripeSubscriptionId: sub.id })
        .where(eq(users.id, userId));

      await bustPlanCache(c.env, userId);
      break;
    }

    // ── Subscription cancelled → downgrade to free ───────────────────────────
    case "customer.subscription.deleted": {
      const sub = event.data.object as any;
      const userId = sub.metadata?.userId;

      if (!userId) break;

      await stripeDb
        .update(users)
        .set({ plan: "free", stripeSubscriptionId: null })
        .where(eq(users.id, userId));

      await bustPlanCache(c.env, userId);

      const [user] = await stripeDb
        .select({ email: users.email, name: users.name })
        .from(users)
        .where(eq(users.id, userId))
        .limit(1);

      if (user) {
        await sendEmail(
          c.env,
          { email: user.email, name: user.name ?? user.email },
          EMAIL_TEMPLATES.PLAN_DOWNGRADED,
          { userId }
        );
      }
      break;
    }

    // ── Payment failed → flag account ────────────────────────────────────────
    case "invoice.payment_failed": {
      const invoice = event.data.object as any;
      const customerId = invoice.customer;

      const [user] = await stripeDb
        .select({ id: users.id, email: users.email, name: users.name })
        .from(users)
        .where(eq(users.stripeCustomerId, customerId))
        .limit(1);

      if (user) {
        await sendEmail(
          c.env,
          { email: user.email, name: user.name ?? user.email },
          EMAIL_TEMPLATES.PAYMENT_FAILED,
          { userId: user.id }
        );
      }
      break;
    }

    default:
      // Unhandled event type — Stripe expects 200 anyway
      break;
  }

  return c.json({ received: true });
});
