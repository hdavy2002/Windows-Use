import { z } from "zod";

// ── Plan limits ───────────────────────────────────────
export const PLAN_LIMITS = {
  free:      { dailyCalls: 100,       liveMode: false, connectors: false },
  pro:       { dailyCalls: Infinity,  liveMode: true,  connectors: true  },
  corporate: { dailyCalls: Infinity,  liveMode: true,  connectors: true  },
} as const;

export type Plan = keyof typeof PLAN_LIMITS;

// ── Telemetry ─────────────────────────────────────────
export const TelemetryPayload = z.object({
  sessionId: z.string().uuid(),
  model: z.string(),
  intent: z.string().max(120).optional(),
  promptTokens: z.number().int().nonnegative(),
  completionTokens: z.number().int().nonnegative(),
  totalTokens: z.number().int().nonnegative(),
  costUsd: z.number().nonnegative(),
  latencyMs: z.number().int().nonnegative(),
  wasCacheHit: z.boolean().default(false),
  capabilityUsed: z.string().optional(),
  mcpToolsCalled: z.array(z.string()).default([]),
});
export type TelemetryPayload = z.infer<typeof TelemetryPayload>;

// ── Sessions ──────────────────────────────────────────
export const SessionStartPayload = z.object({
  mode: z.enum(["chat", "live"]).default("chat"),
  source: z.enum(["web", "desktop"]).default("web"),
});
export type SessionStartPayload = z.infer<typeof SessionStartPayload>;

export const SessionEndPayload = z.object({
  summary: z.string().max(500).optional(),
});

// ── Connectors ────────────────────────────────────────
export const ConnectorAppSchema = z.enum([
  "gmail",
  "outlook",
  "quickbooks",
  "opera_pms",
]);
export type ConnectorApp = z.infer<typeof ConnectorAppSchema>;

export interface ConnectedAppState {
  connectedAt: string;
  accountEmail?: string;
  status: "active" | "error";
}

// ── Billing ───────────────────────────────────────────
export const CheckoutPayload = z.object({
  plan: z.enum(["pro", "corporate"]),
});

// ── AI chat ───────────────────────────────────────────
export const ChatPayload = z.object({
  messages: z.array(
    z.object({
      role: z.enum(["user", "assistant", "system"]),
      content: z.string(),
    })
  ),
  model: z.string().default("anthropic/claude-sonnet-4-5"),
  sessionId: z.string().uuid(),
});
export type ChatPayload = z.infer<typeof ChatPayload>;

// ── Admin stats ───────────────────────────────────────
export const StatsRange = z.enum(["today", "7d", "30d", "all"]);
export type StatsRange = z.infer<typeof StatsRange>;
