/**
 * api-client.ts — Typed fetch wrapper for the Humphi Hono API.
 * Used by both web (Next.js server components + client) and desktop (React).
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined" ? (window as any).__API_URL__ : "") ??
  "http://localhost:8787";

class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API error ${status}`);
  }
}

async function request<T>(
  method: string,
  path: string,
  token?: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, err);
  }

  return res.json() as Promise<T>;
}

const get  = <T>(path: string, token?: string) => request<T>("GET", path, token);
const post = <T>(path: string, body: unknown, token?: string) => request<T>("POST", path, token, body);
const patch = <T>(path: string, body: unknown, token?: string) => request<T>("PATCH", path, token, body);
const del  = <T>(path: string, token?: string) => request<T>("DELETE", path, token);

export const api = {
  users: {
    me: (token: string) => get<{ user: any }>("/users/me", token),
    preferences: (token: string) => get<{ preferences: any }>("/users/me/preferences", token),
    updatePreferences: (prefs: Record<string, unknown>, token: string) =>
      patch<{ ok: boolean }>("/users/me/preferences", prefs, token),
  },

  sessions: {
    start: (opts: { mode: "chat" | "live"; source: "web" | "desktop" }, token: string) =>
      post<{ sessionId: string }>("/sessions/start", opts, token),
    end: (sessionId: string, summary: string | undefined, token: string) =>
      patch<{ ok: boolean }>(`/sessions/${sessionId}/end`, { summary }, token),
    list: (token: string, page = 1) =>
      get<{ sessions: any[] }>(`/sessions?page=${page}`, token),
  },

  telemetry: {
    record: (payload: Record<string, unknown>, token: string) =>
      post<{ ok: boolean; usage: number; limit: number }>("/telemetry", payload, token),
  },

  ai: {
    tools: (token: string, source: "web" | "desktop" = "web") =>
      get<{ tools: any[] }>(`/ai/tools?source=${source}`, token),
  },

  billing: {
    checkout: (plan: "pro" | "corporate", token: string) =>
      post<{ url: string }>("/billing/checkout", { plan }, token),
    portal: (token: string) =>
      post<{ url: string }>("/billing/portal", {}, token),
  },

  connectors: {
    list: (token: string) => get<{ connectors: any[] }>("/connectors", token),
    connect: (app: string, token: string) =>
      post<{ redirectUrl: string }>(`/connectors/${app}/connect`, {}, token),
    disconnect: (app: string, token: string) => del(`/connectors/${app}`, token),
  },

  admin: {
    stats: (range: "today" | "7d" | "30d" | "all", token: string) =>
      get<{ totalUsers: number; totalCalls: number; totalCostUsd: string; activeSessions: number }>(
        `/admin/stats?range=${range}`,
        token
      ),
    users: (params: Record<string, string>, token: string) =>
      get<{ users: any[] }>(`/admin/users?${new URLSearchParams(params)}`, token),
    user: (userId: string, token: string) =>
      get<{ user: any; sessions: any[]; calls: any[] }>(`/admin/users/${userId}`, token),
  },
};

export { ApiError };
