/**
 * composio.ts — Thin wrapper around the Composio REST API.
 * Composio handles OAuth token storage, tool schemas, and action execution.
 * We never store OAuth tokens ourselves — Composio holds them per entityId (= userId).
 */

import type { Env } from "../../types";
import { redis } from "../../lib/redis";

const BASE = "https://backend.composio.dev/api/v1";

// Composio integration IDs for our supported apps
export const APP_INTEGRATION: Record<string, string> = {
  gmail:        "gmail",
  outlook:      "outlook",
  quickbooks:   "quickbooks",
  opera_pms:    "opera_pms",
};

export const SUPPORTED_APPS = Object.keys(APP_INTEGRATION);

// Human-readable app metadata for the UI
export const APP_META: Record<string, { name: string; icon: string; desc: string }> = {
  gmail:      { name: "Gmail",       icon: "📧", desc: "Read, send, search, and draft emails via Gmail." },
  outlook:    { name: "Outlook",     icon: "📨", desc: "Email and calendar via Microsoft 365." },
  quickbooks: { name: "QuickBooks",  icon: "📊", desc: "Invoices, payments, and financial reporting." },
  opera_pms:  { name: "Opera PMS",   icon: "🏨", desc: "Hotel reservations, check-in/out, room charges." },
};

// ── Base request helper ────────────────────────────────────────────────────────

async function composioRequest<T>(
  env: Env,
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "x-api-key": env.COMPOSIO_API_KEY,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Composio ${method} ${path} → ${res.status}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ── Connection management ──────────────────────────────────────────────────────

/**
 * Initiate OAuth for an app. Returns the redirect URL Composio gives the user.
 * `redirectUri` is where Composio sends the user after OAuth completes.
 */
export async function initiateConnection(
  env: Env,
  userId: string,
  app: string,
  redirectUri: string
): Promise<string> {
  const integrationId = APP_INTEGRATION[app];
  if (!integrationId) throw new Error(`Unknown app: ${app}`);

  const data = await composioRequest<{ redirectUrl: string; connectionStatus: string }>(
    env,
    "POST",
    "/connectedAccounts",
    { integrationId, entityId: userId, redirectUri }
  );

  return data.redirectUrl;
}

/**
 * List all connected accounts for a user — returns a map of appName → connectedAccountId.
 */
export async function listConnectedAccounts(
  env: Env,
  userId: string
): Promise<Record<string, string>> {
  const data = await composioRequest<{
    items: Array<{ id: string; appName: string; status: string }>;
  }>(env, "GET", `/connectedAccounts?entityId=${encodeURIComponent(userId)}&pageSize=100`);

  const result: Record<string, string> = {};
  for (const item of data.items ?? []) {
    if (item.status === "ACTIVE") {
      result[item.appName.toLowerCase()] = item.id;
    }
  }
  return result;
}

/**
 * Disconnect an app for a user by removing the connected account.
 */
export async function disconnectApp(
  env: Env,
  userId: string,
  app: string
): Promise<void> {
  const accounts = await listConnectedAccounts(env, userId);
  const accountId = accounts[app];
  if (!accountId) return; // already disconnected
  await composioRequest(env, "DELETE", `/connectedAccounts/${accountId}`);
}

// ── Tool schemas ───────────────────────────────────────────────────────────────

/**
 * Fetch OpenAI-compatible tool schemas for an app, cached in Redis for 10 minutes.
 */
async function fetchToolsForApp(
  env: Env,
  userId: string,
  app: string
): Promise<any[]> {
  const cacheKey = `composio:tools:${userId}:${app}`;
  const r = redis(env);
  const cached = await r.get<any[]>(cacheKey);
  if (cached) return cached;

  const data = await composioRequest<{ items: any[] }>(
    env,
    "GET",
    `/actions?appNames=${encodeURIComponent(app)}&entityId=${encodeURIComponent(userId)}&filterByAvailableApps=true&limit=20`
  );

  const tools = (data.items ?? []).map((action: any) => ({
    type: "function",
    function: {
      name: action.name,           // e.g. "GMAIL_SEND_EMAIL"
      description: action.description ?? `${action.name} via ${app}`,
      parameters: action.parameters ?? { type: "object", properties: {} },
    },
  }));

  await r.set(cacheKey, tools, { ex: 600 });
  return tools;
}

/**
 * Get merged Composio tool schemas for all connected apps.
 * Called at chat time to inject into the OpenRouter request.
 */
export async function getComposioTools(
  env: Env,
  userId: string,
  connectedApps: string[]
): Promise<any[]> {
  const toolArrays = await Promise.allSettled(
    connectedApps.map((app) => fetchToolsForApp(env, userId, app))
  );

  return toolArrays.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
}

/**
 * Invalidate tool cache for a user (call after connect/disconnect).
 */
export async function bustToolCache(env: Env, userId: string): Promise<void> {
  const r = redis(env);
  await Promise.allSettled(
    SUPPORTED_APPS.map((app) => r.del(`composio:tools:${userId}:${app}`))
  );
}

// ── Action execution ───────────────────────────────────────────────────────────

/**
 * Execute a Composio action on behalf of a user.
 * Called by POST /connectors/execute (desktop mcp-client routes here).
 */
export async function executeAction(
  env: Env,
  userId: string,
  actionId: string,
  params: Record<string, unknown>
): Promise<string> {
  const data = await composioRequest<{ successfull: boolean; data: any; error?: string }>(
    env,
    "POST",
    `/actions/${encodeURIComponent(actionId)}/execute`,
    { entityId: userId, input: params }
  );

  if (!data.successfull) {
    throw new Error(data.error ?? "Action execution failed");
  }

  return typeof data.data === "string" ? data.data : JSON.stringify(data.data, null, 2);
}

/**
 * Build a system prompt addendum listing active integrations.
 */
export function buildIntegrationsPrompt(connectedApps: string[]): string {
  if (connectedApps.length === 0) return "";
  const names = connectedApps.map((a) => APP_META[a]?.name ?? a).join(", ");
  return `\n\nThe user has connected the following integrations: ${names}. You can use their tools directly when asked.`;
}
