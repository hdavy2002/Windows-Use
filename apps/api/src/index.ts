import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import { authRoutes } from "./domains/auth/routes";
import { userRoutes } from "./domains/users/routes";
import { sessionRoutes } from "./domains/sessions/routes";
import { telemetryRoutes } from "./domains/telemetry/routes";
import { aiRoutes } from "./domains/ai/routes";
import { adminRoutes } from "./domains/admin/routes";
import { billingRoutes } from "./domains/billing/routes";
import { connectorRoutes } from "./domains/connectors/routes";
import { inngest, inngestServe } from "./lib/inngest";
import type { Env, Variables } from "./types";

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

// ── Global middleware ─────────────────────────────────
app.use("*", logger());

app.use(
  "*",
  cors({
    origin: (origin) => {
      const allowed = [
        "https://humphi.ai",
        "https://www.humphi.ai",
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:3000",
        "http://localhost:5173",
      ];
      return allowed.includes(origin) ? origin : null;
    },
    allowHeaders: ["Content-Type", "Authorization", "X-Source"],
    credentials: true,
  })
);

// ── Routes ────────────────────────────────────────────
app.route("/auth", authRoutes);
app.route("/users", userRoutes);
app.route("/sessions", sessionRoutes);
app.route("/telemetry", telemetryRoutes);
app.route("/ai", aiRoutes);
app.route("/admin", adminRoutes);
app.route("/billing", billingRoutes);
app.route("/connectors", connectorRoutes);

// Inngest — serves the function registry; Inngest cloud calls back here
app.on(
  ["GET", "POST", "PUT"],
  "/api/inngest",
  inngestServe({ client: inngest, functions: [] }) // functions added in Phase 4+
);

// ── Health check ──────────────────────────────────────
app.get("/health", (c) => c.json({ ok: true, ts: new Date().toISOString() }));

// ── Global error handler ──────────────────────────────
app.onError((err, c) => {
  const id = crypto.randomUUID();
  console.error(`[${id}]`, err);
  return c.json({ error: "Internal server error", errorId: id }, 500);
});

app.notFound((c) => c.json({ error: "Not found" }, 404));

export default app;
