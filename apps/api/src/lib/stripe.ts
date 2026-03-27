import Stripe from "stripe";
import type { Env } from "../types";

/**
 * Returns a Stripe client scoped to this request's env bindings.
 * CF Workers don't support persistent module-level singletons with
 * env values, so we create one per request (cheap — no I/O).
 */
export function stripe(env: Env) {
  return new Stripe(env.STRIPE_SECRET_KEY, {
    // @ts-expect-error — CF Workers runtime is not in the official list but works fine
    httpClient: Stripe.createFetchHttpClient(),
    apiVersion: "2025-03-31.basil",
  });
}
