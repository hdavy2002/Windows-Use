import { pgTable, text, timestamp, uuid, integer, numeric, boolean, jsonb } from "drizzle-orm/pg-core";

// ── Users ────────────────────────────────────────────
export const users = pgTable("users", {
  id: text("id").primaryKey(),              // Clerk user ID
  email: text("email").notNull(),
  name: text("name"),
  plan: text("plan").default("free"),       // free / pro / corporate
  role: text("role").default("user"),       // user / admin
  createdAt: timestamp("created_at").defaultNow(),
});

// ── Sessions ─────────────────────────────────────────
export const sessions = pgTable("sessions", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").references(() => users.id),
  startedAt: timestamp("started_at").defaultNow(),
  endedAt: timestamp("ended_at"),
  summary: text("summary"),
  mode: text("mode").default("chat"),       // chat / live
});

// ── API Calls (full token breakdown) ─────────────────
export const apiCalls = pgTable("api_calls", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").references(() => users.id),
  sessionId: uuid("session_id").references(() => sessions.id),
  timestamp: timestamp("timestamp").defaultNow(),
  model: text("model").notNull(),
  intent: text("intent"),
  // Token breakdown
  promptTokens: integer("prompt_tokens"),
  completionTokens: integer("completion_tokens"),
  totalTokens: integer("total_tokens"),
  memoryTokensInjected: integer("memory_tokens_injected"),
  systemTokens: integer("system_tokens"),
  // Cost + performance
  costUsd: numeric("cost_usd", { precision: 10, scale: 6 }),
  latencyMs: integer("latency_ms"),
  // Metadata
  wasCacheHit: boolean("was_cache_hit").default(false),
  capabilityUsed: text("capability_used"),
  mcpToolsCalled: text("mcp_tools_called"),   // JSON array string
});

// ── mem0 Memories ────────────────────────────────────
export const memories = pgTable("memories", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").references(() => users.id),
  key: text("key").notNull(),
  value: jsonb("value").notNull(),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

// ── User Preferences ─────────────────────────────────
export const preferences = pgTable("preferences", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").references(() => users.id).unique(),
  voiceName: text("voice_name").default("Aoede"),
  theme: text("theme").default("dark"),
  connectedApps: jsonb("connected_apps").default("[]"),
  updatedAt: timestamp("updated_at").defaultNow(),
});
