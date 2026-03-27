import { Inngest } from "inngest";

// Single Inngest client — env vars injected at request time via middleware
export const inngest = new Inngest({ id: "humphi-ai" });

// Re-export serve for use in index.ts
export { serve as inngestServe } from "inngest/hono";
