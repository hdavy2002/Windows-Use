import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { ChatPayload, PLAN_LIMITS } from "@humphi/types";
import { users, preferences } from "@humphi/db";
import { eq } from "drizzle-orm";
import { db } from "../../lib/db";
import { getDailyUsage, getPlanFromCache, setPlanCache } from "../../lib/redis";
import { requireAuth } from "../auth/middleware";
import type { Env, Variables } from "../../types";

export const aiRoutes = new Hono<{ Bindings: Env; Variables: Variables }>();

// Desktop commander tools — always available on desktop
const DESKTOP_TOOLS = [
  { type: "function", function: { name: "execute_command", description: "Run a PowerShell command on the user's Windows PC.", parameters: { type: "object", properties: { command: { type: "string" } }, required: ["command"] } } },
  { type: "function", function: { name: "read_file", description: "Read the contents of a file.", parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] } } },
  { type: "function", function: { name: "write_file", description: "Write content to a file.", parameters: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] } } },
  { type: "function", function: { name: "list_directory", description: "List files and folders in a directory.", parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] } } },
  { type: "function", function: { name: "search_files", description: "Search for files matching a pattern.", parameters: { type: "object", properties: { pattern: { type: "string" }, directory: { type: "string" } }, required: ["pattern"] } } },
  { type: "function", function: { name: "open_application", description: "Open an application by name.", parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } },
  { type: "function", function: { name: "get_system_info", description: "Get system information and top processes.", parameters: { type: "object", properties: {} } } },
  { type: "function", function: { name: "get_clipboard", description: "Get the current clipboard text.", parameters: { type: "object", properties: {} } } },
  { type: "function", function: { name: "set_clipboard", description: "Set text to the clipboard.", parameters: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } } },
];

const SYSTEM_PROMPT = `You are Humphi, an AI desktop assistant. You help users with their Windows PC — running commands, reading files, opening apps, and more. Be concise and direct. Always confirm before running destructive operations. Never delete files without explicit confirmation.`;

// POST /ai/chat — streaming proxy through CF AI Gateway
aiRoutes.post("/chat", requireAuth, zValidator("json", ChatPayload), async (c) => {
  const userId = c.get("userId");
  const { messages, model, sessionId } = c.req.valid("json");
  const source = c.req.header("X-Source") ?? "web"; // 'web' | 'desktop'

  // Check plan limit before spending tokens
  let plan = await getPlanFromCache(c.env, userId);
  if (!plan) {
    const [user] = await db(c.env).select({ plan: users.plan }).from(users).where(eq(users.id, userId)).limit(1);
    plan = user?.plan ?? "free";
    await setPlanCache(c.env, userId, plan);
  }
  const limit = PLAN_LIMITS[plan as keyof typeof PLAN_LIMITS].dailyCalls;
  const usage = await getDailyUsage(c.env, userId);
  if (usage >= limit) {
    return c.json({ error: "Daily limit reached. Upgrade your plan to continue." }, 429);
  }

  // Build tools based on source + connected apps
  const tools = source === "desktop" ? DESKTOP_TOOLS : [];

  const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${c.env.CF_ACCOUNT_ID}/${c.env.CF_GATEWAY_NAME}/openrouter/chat/completions`;

  const upstream = await fetch(gatewayUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${c.env.OPENROUTER_API_KEY}`,
      "cf-aig-authorization": `Bearer ${c.env.CF_AIG_TOKEN}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://humphi.ai",
      "X-Title": "Humphi AI",
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
      stream: true,
      ...(tools.length > 0 ? { tools } : {}),
    }),
  });

  if (!upstream.ok) {
    const err = await upstream.text();
    return c.json({ error: "AI request failed", detail: err }, 502);
  }

  // Stream the SSE response directly back
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
});

// GET /ai/tools — returns tool list for client display
aiRoutes.get("/tools", requireAuth, async (c) => {
  const source = c.req.query("source") ?? "web";
  const tools = source === "desktop" ? DESKTOP_TOOLS : [];
  return c.json({ tools });
});
