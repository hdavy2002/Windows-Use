export type Env = {
  // Neon
  NEON_DATABASE_URL: string;
  // Upstash
  UPSTASH_REDIS_URL: string;
  UPSTASH_REDIS_TOKEN: string;
  // Clerk
  CLERK_SECRET_KEY: string;
  // Inngest
  INNGEST_SIGNING_KEY: string;
  INNGEST_EVENT_KEY: string;
  // Stripe
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_PRICE_PRO: string;
  STRIPE_PRICE_CORPORATE: string;
  // Cloudflare AI Gateway
  OPENROUTER_API_KEY: string;
  CF_AIG_TOKEN: string;
  CF_ACCOUNT_ID: string;
  CF_GATEWAY_NAME: string;
  // Composio
  COMPOSIO_API_KEY: string;
  // Brevo
  BREVO_API_KEY: string;
  // URLs
  WEB_URL: string;
  API_URL: string;
};

// Hono context variables set by middleware
export type Variables = {
  userId: string;
};
