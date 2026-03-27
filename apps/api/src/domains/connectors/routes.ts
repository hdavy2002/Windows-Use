import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { eq } from "drizzle-orm";
import { preferences } from "@humphi/db";
import { db } from "../../lib/db";
import { checkRateLimit } from "../../lib/redis";
import { requireAuth } from "../auth/middleware";
import {
  APP_META,
  SUPPORTED_APPS,
  initiateConnection,
  disconnectApp,
  executeAction,
  listConnectedAccounts,
  bustToolCache,
} from "./composio";
import type { Env, Variables } from "../../types";

export const connectorRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// ── GET /connectors ────────────────────────────────────────────────────────────
// Returns all supported connectors with connected state for this user.
connectorRoutes.get("/", requireAuth, async (c) => {
  const userId = c.get("userId");

  const [prefs] = await db(c.env)
    .select({ connectedApps: preferences.connectedApps })
    .from(preferences)
    .where(eq(preferences.userId, userId))
    .limit(1);

  const connectedApps = (prefs?.connectedApps as Record<string, any>) ?? {};

  const connectors = SUPPORTED_APPS.map((app) => ({
    id: app,
    ...APP_META[app],
    connected: !!connectedApps[app]?.status,
    connectedAt: connectedApps[app]?.connectedAt ?? null,
    accountEmail: connectedApps[app]?.accountEmail ?? null,
  }));

  return c.json({ connectors });
});

// ── POST /connectors/:app/connect ─────────────────────────────────────────────
// Initiates OAuth for an app via Composio. Returns { redirectUrl }.
connectorRoutes.post("/:app/connect", requireAuth, async (c) => {
  const userId = c.get("userId");
  const app = c.req.param("app");

  if (!SUPPORTED_APPS.includes(app)) {
    return c.json({ error: `Unknown connector: ${app}` }, 400);
  }

  // Rate limit: max 10 OAuth initiations per hour per user
  const { allowed } = await checkRateLimit(c.env, `oauth:${userId}`, 10, 3600);
  if (!allowed) {
    return c.json({ error: "Too many connection attempts. Try again in an hour." }, 429);
  }

  const redirectUri = `${c.env.WEB_URL}/dashboard/connectors?connected=${app}`;

  const redirectUrl = await initiateConnection(c.env, userId, app, redirectUri);
  return c.json({ redirectUrl });
});

// ── DELETE /connectors/:app ────────────────────────────────────────────────────
// Disconnects an app for the user — revokes Composio tokens + clears preferences.
connectorRoutes.delete("/:app", requireAuth, async (c) => {
  const userId = c.get("userId");
  const app = c.req.param("app");

  if (!SUPPORTED_APPS.includes(app)) {
    return c.json({ error: `Unknown connector: ${app}` }, 400);
  }

  await disconnectApp(c.env, userId, app);

  // Remove from preferences
  const [prefs] = await db(c.env)
    .select({ connectedApps: preferences.connectedApps })
    .from(preferences)
    .where(eq(preferences.userId, userId))
    .limit(1);

  const connectedApps = { ...((prefs?.connectedApps as Record<string, any>) ?? {}) };
  delete connectedApps[app];

  await db(c.env)
    .insert(preferences)
    .values({ userId, connectedApps })
    .onConflictDoUpdate({
      target: preferences.userId,
      set: { connectedApps, updatedAt: new Date() },
    });

  await bustToolCache(c.env, userId);

  return c.json({ ok: true });
});

// ── POST /connectors/callback ──────────────────────────────────────────────────
// Called by our web app after Composio OAuth redirect — records the connection.
// Composio redirects to WEB_URL/dashboard/connectors?connected={app}
// The web page calls this to finalise and persist the connection state.
connectorRoutes.post(
  "/callback",
  requireAuth,
  zValidator("json", z.object({ app: z.string() })),
  async (c) => {
    const userId = c.get("userId");
    const { app } = c.req.valid("json");

    if (!SUPPORTED_APPS.includes(app)) {
      return c.json({ error: `Unknown app: ${app}` }, 400);
    }

    // Verify the account is actually active in Composio
    const accounts = await listConnectedAccounts(c.env, userId);
    const connected = !!accounts[app];

    if (connected) {
      const [prefs] = await db(c.env)
        .select({ connectedApps: preferences.connectedApps })
        .from(preferences)
        .where(eq(preferences.userId, userId))
        .limit(1);

      const connectedApps = {
        ...((prefs?.connectedApps as Record<string, any>) ?? {}),
        [app]: { connectedAt: new Date().toISOString(), status: "active" },
      };

      await db(c.env)
        .insert(preferences)
        .values({ userId, connectedApps })
        .onConflictDoUpdate({
          target: preferences.userId,
          set: { connectedApps, updatedAt: new Date() },
        });

      await bustToolCache(c.env, userId);
    }

    return c.json({ ok: connected });
  }
);

// ── POST /connectors/execute ───────────────────────────────────────────────────
// Executes a Composio action on behalf of the user.
// Called by the desktop mcp-client for non-local (Composio) tools.
connectorRoutes.post(
  "/execute",
  requireAuth,
  zValidator(
    "json",
    z.object({
      actionId: z.string(),
      params: z.record(z.unknown()).default({}),
    })
  ),
  async (c) => {
    const userId = c.get("userId");
    const { actionId, params } = c.req.valid("json");

    const result = await executeAction(c.env, userId, actionId, params);
    return c.json({ result });
  }
);
