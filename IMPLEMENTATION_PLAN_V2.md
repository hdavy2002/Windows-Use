# Humphi AI — Implementation Plan V2
**Stack: Hono on CF Workers · Drizzle + Neon · Upstash Redis · Inngest · Clerk · Stripe · Brevo · Composio · Tauri + Rust**

---

## Architectural Principles

1. **Single backend, two frontends** — Hono API on Cloudflare Workers serves both Next.js web and Tauri desktop. All business logic lives in the API. Both frontends are pure UI.
2. **Domain-driven structure** — organized by business domain: auth, users, sessions, telemetry, billing, connectors, ai, admin.
3. **Feature parity** — every feature on the web dashboard is available in the desktop UI.
4. **No Next.js API routes** — all existing `web/src/app/api/*` routes migrate to Hono domains.
5. **No Temporal** — use Inngest for all scheduled jobs, event-driven workflows, and fan-out tasks. Inngest calls back into the Hono Worker via HTTP. No persistent process needed.

---

## Scheduling Strategy — Inngest

Inngest handles everything: cron jobs, event-driven workflows, fan-out, delays, retries. One SDK. Inngest's cloud calls back into your Hono Worker at `POST /api/inngest`. Works natively with Cloudflare Workers.

| Job | Inngest trigger | Notes |
|-----|----------------|-------|
| Daily usage reset (midnight) | `{ cron: "0 0 * * *" }` | Function definition, no wrangler.toml cron needed |
| Session cleanup (every hour) | `{ cron: "0 * * * *" }` | Same |
| Weekly user reports (Sunday 8am) | `{ cron: "0 8 * * 0" }` → fan-out with `step.sendEvent` | One event per user, each retried independently |
| Usage alert at 80%/100% | `inngest.send("usage/alert", data)` from telemetry route | Event-driven, fires inline |
| Billing reminders | `{ cron: "0 9 1 * *" }` → fan-out | Same pattern as weekly reports |
| Stripe webhook retries | Stripe handles natively | No Inngest needed |

```typescript
// apps/api/src/lib/inngest.ts
import { Inngest } from 'inngest'
export const inngest = new Inngest({ id: 'humphi-ai', signingKey: process.env.INNGEST_SIGNING_KEY })

// Cron function example
export const dailyReset = inngest.createFunction(
  { id: 'daily-reset' },
  { cron: '0 0 * * *' },
  async ({ step }) => {
    await step.run('session-cleanup', () => sessionCleanup())
  }
)

// Event-driven function example
export const usageAlertFn = inngest.createFunction(
  { id: 'usage-alert', retries: 3 },
  { event: 'usage/alert' },
  async ({ event, step }) => {
    await step.run('send-email', () => sendUsageAlertEmail(event.data))
  }
)

// In Hono index.ts — Inngest calls this to run functions
import { serve } from 'inngest/hono'
app.on(['GET', 'POST', 'PUT'], '/api/inngest', serve({ client: inngest, functions: [dailyReset, usageAlertFn, ...] }))
```

---

## Monorepo Structure

```
Windows-Use/
├── apps/
│   ├── api/                        # Hono on Cloudflare Workers
│   │   ├── src/
│   │   │   ├── domains/            # auth, users, sessions, telemetry, billing, connectors, ai, admin
│   │   │   ├── lib/                # db, redis, inngest, brevo, stripe, composio
│   │   │   └── index.ts            # Hono app entry, all routes mounted
│   │   └── wrangler.toml
│   ├── web/                        # Next.js 16 — UI only
│   └── desktop/                    # Tauri + React — UI only
├── packages/
│   ├── db/                         # Drizzle schema + migrations (shared)
│   ├── types/                      # Shared Zod schemas + TypeScript types
│   └── ui/                         # Shared React components (shadcn/ui)
├── pnpm-workspace.yaml
├── package.json
└── turbo.json
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Router | Hono.dev on Cloudflare Workers |
| ORM | Drizzle + Neon HTTP (edge-compatible) |
| Auth | Clerk (JWT verification in Hono middleware) |
| Caching + Rate Limiting | Upstash Redis |
| Scheduled + Async Jobs | Inngest |
| Transactional Email | Brevo |
| Billing | Stripe |
| MCP Connectors | Composio + custom MCP servers |
| AI Gateway | Cloudflare AI Gateway |
| AI Live | Gemini Live API via Rust WebSocket |
| Desktop Runtime | Tauri 2 + Rust |
| Web UI | Next.js 16 (Vercel) |
| Desktop UI | React 19 + Tauri |
| Shared UI | shadcn/ui + Tailwind v4 |
| Monorepo | pnpm workspaces + Turborepo |

---

---

# Phase 1 — Week 1-2: Core Foundation
**Ship target:** Desktop app opens, Clerk sign-in works, user can chat with Claude, messages stored in Neon.

---

## 1.1 — Monorepo Setup

**New files:** `pnpm-workspace.yaml`, root `package.json`, `turbo.json`

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

Steps:
1. Move `desktop/` → `apps/desktop/`
2. Move `web/` → `apps/web/`
3. Create `apps/api/` (new Hono worker)
4. Create `packages/db/` — move Drizzle schema here, shared by API and web
5. Create `packages/types/` — shared Zod schemas
6. Update all `tsconfig.json` path references
7. Verify `pnpm install` at root resolves all workspaces

---

## 1.2 — packages/db Schema

**File:** `packages/db/src/schema.ts`

Keep existing 5 tables. Add:
```typescript
// Add to users
stripeCustomerId: text('stripe_customer_id'),
stripeSubscriptionId: text('stripe_subscription_id'),

// Add to sessions
source: text('source').default('web'),   // 'web' | 'desktop'

// New table
export const notifications = pgTable('notifications', {
  id: uuid('id').primaryKey().defaultRandom(),
  userId: text('user_id').references(() => users.id),
  type: text('type').notNull(),           // 'usage_80' | 'usage_100' | 'billing_reminder' | 'weekly_report'
  sentAt: timestamp('sent_at').defaultNow(),
})
```

Run `drizzle-kit generate && drizzle-kit migrate`.

---

## 1.3 — Hono API Scaffold

**File:** `apps/api/wrangler.toml`

```toml
name = "humphi-api"
main = "src/index.ts"
compatibility_date = "2024-11-01"
compatibility_flags = ["nodejs_compat"]

[vars]
WEB_URL = "https://humphi.ai"

# Cron jobs
[[triggers.crons]]
crons = ["0 0 * * *"]    # daily reset — midnight UTC
[[triggers.crons]]
crons = ["0 * * * *"]    # session cleanup — every hour
[[triggers.crons]]
crons = ["0 8 * * 0"]    # weekly report — Sunday 8am UTC
[[triggers.crons]]
crons = ["0 9 1 * *"]    # billing reminders — 1st of month 9am UTC

# Secrets via: wrangler secret put <NAME>
# CLERK_SECRET_KEY, NEON_DATABASE_URL, UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN,
# INNGEST_SIGNING_KEY, INNGEST_EVENT_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
# OPENROUTER_API_KEY, CF_AIG_TOKEN, CF_ACCOUNT_ID, CF_GATEWAY_NAME,
# COMPOSIO_API_KEY, BREVO_API_KEY
```

**File:** `apps/api/src/index.ts`

```typescript
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { logger } from 'hono/logger'

export type Env = {
  CLERK_SECRET_KEY: string
  NEON_DATABASE_URL: string
  UPSTASH_REDIS_URL: string
  UPSTASH_REDIS_TOKEN: string
  INNGEST_SIGNING_KEY: string
  INNGEST_EVENT_KEY: string
  STRIPE_SECRET_KEY: string
  STRIPE_WEBHOOK_SECRET: string
  OPENROUTER_API_KEY: string
  CF_AIG_TOKEN: string
  CF_ACCOUNT_ID: string
  CF_GATEWAY_NAME: string
  COMPOSIO_API_KEY: string
  BREVO_API_KEY: string
  WEB_URL: string
}

const app = new Hono<{ Bindings: Env }>()

app.use('*', logger())
app.use('*', cors({
  origin: (origin) => ['https://humphi.ai', 'tauri://localhost', 'http://tauri.localhost'].includes(origin) ? origin : null,
  credentials: true,
}))

// Domain routes
app.route('/auth', authRoutes)
app.route('/users', userRoutes)
app.route('/sessions', sessionRoutes)
app.route('/telemetry', telemetryRoutes)
app.route('/billing', billingRoutes)
app.route('/connectors', connectorRoutes)
app.route('/ai', aiRoutes)
app.route('/admin', adminRoutes)
// Inngest serve — Inngest cloud calls this to execute functions
app.on(['GET', 'POST', 'PUT'], '/api/inngest', serve({ client: inngest, functions: allInngestFunctions }))

export default app
```

---

## 1.4 — Auth Middleware

**File:** `apps/api/src/domains/auth/middleware.ts`

```typescript
import { verifyToken } from '@clerk/backend'

export const requireAuth = createMiddleware<{ Bindings: Env }>(async (c, next) => {
  const token = c.req.header('Authorization')?.replace('Bearer ', '')
  if (!token) return c.json({ error: 'Unauthorized' }, 401)
  const payload = await verifyToken(token, { secretKey: c.env.CLERK_SECRET_KEY })
  c.set('userId', payload.sub)
  await next()
})
```

**File:** `apps/api/src/domains/auth/routes.ts`

```typescript
// POST /auth/clerk-webhook — Clerk fires this on user.created
authRouter.post('/clerk-webhook', async (c) => {
  const { type, data } = await c.req.json()
  if (type === 'user.created') {
    await db(c.env).insert(users).values({
      id: data.id,
      email: data.email_addresses[0].email_address,
      name: `${data.first_name} ${data.last_name}`.trim(),
      plan: 'free',
      role: 'user',
    }).onConflictDoNothing()
  }
  return c.json({ ok: true })
})
```

---

## 1.5 — AI Domain (CF Gateway)

**File:** `apps/api/src/domains/ai/routes.ts`

```typescript
// POST /ai/chat — authenticated streaming proxy through Cloudflare AI Gateway
aiRouter.post('/chat', requireAuth, async (c) => {
  const userId = c.get('userId')
  const { messages, model, sessionId } = await c.req.json()

  // Check daily limit (Redis counter)
  const usage = await getDailyUsage(c.env, userId)
  const limit = await getPlanLimit(c.env, userId)
  if (usage >= limit) return c.json({ error: 'Daily limit reached. Upgrade your plan.' }, 429)

  const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${c.env.CF_ACCOUNT_ID}/${c.env.CF_GATEWAY_NAME}/openrouter/chat/completions`

  const upstream = await fetch(gatewayUrl, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${c.env.OPENROUTER_API_KEY}`,
      'cf-aig-authorization': `Bearer ${c.env.CF_AIG_TOKEN}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://humphi.ai',
    },
    body: JSON.stringify({ model: model ?? 'anthropic/claude-sonnet-4-5', messages, stream: true }),
  })

  // Pass the SSE stream straight back to the client
  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
    },
  })
})

// GET /ai/tools — returns tool list based on user's connected apps + source
aiRouter.get('/tools', requireAuth, async (c) => {
  const userId = c.get('userId')
  const source = c.req.query('source') ?? 'web'        // 'web' | 'desktop'
  const prefs = await getPreferences(c.env, userId)
  const tools = await buildToolList(prefs.connectedApps, source)
  return c.json({ tools })
})
```

---

## 1.6 — Telemetry Domain

**File:** `apps/api/src/domains/telemetry/routes.ts`

```typescript
telemetryRouter.post('/', requireAuth, zValidator('json', TelemetryPayload), async (c) => {
  const userId = c.get('userId')
  const body = c.req.valid('json')

  // Increment Redis daily counter
  const usage = await incrementDailyUsage(c.env, userId)
  const limit = await getPlanLimit(c.env, userId)

  // Insert to Neon
  await db(c.env).insert(apiCalls).values({ userId, ...body })

  // Trigger usage alert inline — no scheduler needed
  const threshold = usage === Math.floor(limit * 0.8) ? 80 : usage >= limit ? 100 : null
  if (threshold) {
    const notifKey = `notif:${userId}:usage_${threshold}:${today()}`
    const alreadySent = await redis(c.env).get(notifKey)
    if (!alreadySent) {
      await redis(c.env).set(notifKey, '1', { ex: 86400 })
      await sendUsageAlertEmail(c.env, userId, usage, limit, threshold)
    }
  }

  return c.json({ ok: true, usage, limit })
})
```

---

## 1.7 — Upstash Redis Helpers

**File:** `apps/api/src/lib/redis.ts`

```typescript
import { Redis } from '@upstash/redis/cloudflare'

export const redis = (env: Env) => new Redis({ url: env.UPSTASH_REDIS_URL, token: env.UPSTASH_REDIS_TOKEN })

export async function incrementDailyUsage(env: Env, userId: string) {
  const r = redis(env)
  const key = `usage:daily:${userId}:${today()}`
  const count = await r.incr(key)
  if (count === 1) await r.expire(key, 86400)
  return count
}

export async function getDailyUsage(env: Env, userId: string) {
  return (await redis(env).get<number>(`usage:daily:${userId}:${today()}`)) ?? 0
}

export async function getPlanLimit(env: Env, userId: string): Promise<number> {
  const cached = await redis(env).get<string>(`plan:${userId}`)
  const plan = cached ?? (await getUserById(env, userId)).plan
  if (!cached) await redis(env).set(`plan:${userId}`, plan, { ex: 300 })
  return PLAN_LIMITS[plan].dailyCalls
}

export async function checkRateLimit(env: Env, key: string, limit: number, windowSecs: number) {
  const r = redis(env)
  const count = await r.incr(`ratelimit:${key}`)
  if (count === 1) await r.expire(`ratelimit:${key}`, windowSecs)
  return { allowed: count <= limit, count }
}

export const PLAN_LIMITS = {
  free:      { dailyCalls: 100,      liveMode: false, connectors: false },
  pro:       { dailyCalls: Infinity, liveMode: true,  connectors: true },
  corporate: { dailyCalls: Infinity, liveMode: true,  connectors: true },
}
```

---

## 1.8 — Frontend API Client (Web + Desktop)

**File:** `apps/web/src/lib/api-client.ts`
**File:** `apps/desktop/src/lib/api-client.ts`

Same shape, different base URL env var:

```typescript
const API_URL = import.meta.env.VITE_API_URL ?? process.env.NEXT_PUBLIC_API_URL

async function request(method: string, path: string, body?: unknown, token?: string) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new ApiError(res.status, await res.json())
  return res
}

export const api = {
  ai:         { chat: (msgs, model, sessionId, token) => request('POST', '/ai/chat', { messages: msgs, model, sessionId }, token) },
  telemetry:  { record: (payload, token) => request('POST', '/telemetry', payload, token) },
  sessions:   { start: (opts, token) => request('POST', '/sessions/start', opts, token), end: (id, summary, token) => request('PATCH', `/sessions/${id}/end`, { summary }, token) },
  users:      { me: (token) => request('GET', '/users/me', undefined, token), updatePrefs: (prefs, token) => request('PATCH', '/users/me/preferences', prefs, token) },
  billing:    { checkout: (plan, token) => request('POST', '/billing/checkout', { plan }, token), portal: (token) => request('POST', '/billing/portal', {}, token) },
  connectors: { list: (token) => request('GET', '/connectors', undefined, token), connect: (app, token) => request('POST', `/connectors/${app}/connect`, {}, token), disconnect: (app, token) => request('DELETE', `/connectors/${app}`, undefined, token) },
  admin:      { stats: (range, token) => request('GET', `/admin/stats?range=${range}`, undefined, token), users: (q, token) => request('GET', `/admin/users?${new URLSearchParams(q)}`, undefined, token) },
}
```

---

## 1.9 — Desktop: Replace Login with Clerk + Wire to API

**File:** `apps/desktop/src/App.tsx`

```tsx
import { ClerkProvider, SignedIn, SignedOut, SignIn, useAuth } from '@clerk/clerk-react'

function App() {
  return (
    <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}>
      <SignedOut>
        <div className="flex items-center justify-center h-screen bg-[#0a0c10]">
          <SignIn routing="hash" />
        </div>
      </SignedOut>
      <SignedIn>
        <AppShell />
      </SignedIn>
    </ClerkProvider>
  )
}
```

**File:** `apps/desktop/src/lib/ai-engine.ts`

Update to call `POST /ai/chat` on Hono instead of OpenRouter directly:
```typescript
const token = await getToken()   // from useAuth()
const res = await api.ai.chat(messages, model, sessionId, token)
// res.body is an SSE stream — read with getReader() same as before
```

Remove all hardcoded OpenRouter URLs, API key references, and localStorage key logic.

---

## 1.10 — Web: Replace Next.js API Routes

Delete:
- `web/src/app/api/telemetry/route.ts` → now `POST /telemetry` in Hono
- `web/src/app/api/webhooks/clerk/route.ts` → now `POST /auth/clerk-webhook` in Hono

Update all web dashboard pages to call `api.*` client instead of fetch('/api/...')`.

---

## Phase 1 Deliverables Checklist
- [ ] pnpm monorepo with 3 apps + 2 packages
- [ ] Hono Worker deployed to `api.humphi.ai`
- [ ] Clerk auth working in both desktop (hash routing) and web
- [ ] Desktop chat calls `/ai/chat` → CF Gateway → Claude → SSE back
- [ ] Every message POSTs to `/telemetry` → Neon `api_calls` row created
- [ ] Session start/end tracked in `sessions` table
- [ ] Wrangler secrets all set

---

---

# Phase 2 — Week 3-4: DesktopCommanderMCP + v0.1 Ship
**Ship target:** "Open Excel" and "Read this file" work. 5 test users.

---

## 2.1 — Expand Rust Tool Set in lib.rs

**File:** `apps/desktop/src-tauri/src/lib.rs`

Add to existing 5 tools (execute_command, read_file, write_file, list_directory, search_files):

```rust
// Cargo.toml additions
// arboard = "3"    ← clipboard

"get_file_info" => {
    let path = args["path"].as_str().ok_or("missing path")?;
    let meta = std::fs::metadata(path).map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "size": meta.len(), "is_dir": meta.is_dir(), "readonly": meta.permissions().readonly() }).to_string())
}
"move_file" => {
    std::fs::rename(args["source"].as_str().unwrap(), args["destination"].as_str().unwrap()).map_err(|e| e.to_string())?;
    Ok("moved".to_string())
}
"create_directory" => {
    std::fs::create_dir_all(args["path"].as_str().unwrap()).map_err(|e| e.to_string())?;
    Ok("created".to_string())
}
"get_clipboard" => {
    arboard::Clipboard::new().map_err(|e| e.to_string())?.get_text().map_err(|e| e.to_string())
}
"set_clipboard" => {
    arboard::Clipboard::new().map_err(|e| e.to_string())?.set_text(args["text"].as_str().unwrap()).map_err(|e| e.to_string())?;
    Ok("set".to_string())
}
"open_application" => {
    Command::new("cmd").args(["/c", "start", "", args["name"].as_str().unwrap()]).spawn().map_err(|e| e.to_string())?;
    Ok("launched".to_string())
}
"kill_process" => {
    Command::new("powershell").args(["-Command", &format!("Stop-Process -Name '{}' -Force", args["name"].as_str().unwrap())]).output().map_err(|e| e.to_string())?;
    Ok("killed".to_string())
}
"get_system_info" => {
    let out = Command::new("powershell").args(["-Command", "Get-ComputerInfo | Select CsName,OsName; Get-Process | Sort CPU -Desc | Select -First 10 Name,CPU | ConvertTo-Json"]).output().map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}
```

---

## 2.2 — Update Tool Schemas in AI Engine

**File:** `apps/desktop/src/lib/ai-engine.ts`

Since tool schemas now live in the API (`GET /ai/tools`), the desktop fetches them on session start:

```typescript
const { tools } = await api.ai.tools(token)  // returns all DC_TOOLS + connected app tools
```

Keep DC_TOOLS as the fallback/default. Eventually all tool definitions live server-side so both web and desktop get the same list.

---

## 2.3 — Sessions Domain

**File:** `apps/api/src/domains/sessions/routes.ts`

```typescript
// POST /sessions/start
sessionsRouter.post('/start', requireAuth, async (c) => {
  const userId = c.get('userId')
  const { mode, source } = await c.req.json()
  const session = await db(c.env).insert(sessions).values({ userId, mode, source }).returning()
  await redis(c.env).set(`session:${session[0].id}`, userId, { ex: 7200 })
  return c.json({ sessionId: session[0].id })
})

// PATCH /sessions/:id/end
sessionsRouter.patch('/:id/end', requireAuth, async (c) => {
  const id = c.req.param('id')
  const { summary } = await c.req.json()
  await db(c.env).update(sessions).set({ endedAt: new Date(), summary }).where(eq(sessions.id, id))
  await redis(c.env).del(`session:${id}`)
  return c.json({ ok: true })
})

// GET /sessions — list user's sessions
sessionsRouter.get('/', requireAuth, async (c) => {
  const userId = c.get('userId')
  const page = Number(c.req.query('page') ?? 1)
  const rows = await db(c.env).select().from(sessions).where(eq(sessions.userId, userId)).orderBy(desc(sessions.startedAt)).limit(20).offset((page - 1) * 20)
  return c.json({ sessions: rows })
})
```

---

## 2.4 — Real Dashboard Data

Replace all hardcoded `0` values:

**`apps/web/src/app/dashboard/page.tsx`**
```typescript
const stats = await api.admin.stats('today', token)
// { totalCalls, totalTokens, totalCostUsd, activeSessions }
```

**`apps/web/src/app/dashboard/history/page.tsx`**
```typescript
const { sessions } = await api.sessions.list(token)
// Render table: date, mode, source (web/desktop), messages, cost
```

---

## 2.5 — v0.1 Pre-Ship Checklist
- [ ] "Open Excel" → `open_application` tool → Excel launches
- [ ] "Read the file at C:\reports\q4.xlsx" → `read_file` tool → contents returned to AI
- [ ] "Search for all PDFs in Documents" → `search_files` tool → list returned
- [ ] "Copy this text to clipboard" → `set_clipboard` tool works
- [ ] Session history shows in web dashboard
- [ ] Desktop shows real user name from Clerk
- [ ] Deploy API to `api.humphi.ai` via `wrangler deploy`
- [ ] 5 test users signed up and using it

---

---

# Phase 3 — Week 5-6: Gemini Live (v0.2 — Killer Feature)
**Ship target:** User says "help me fix this formula", Gemini watches their screen and talks them through it.

---

## 3.1 — Cargo Dependencies

**File:** `apps/desktop/src-tauri/Cargo.toml`

```toml
tokio = { version = "1", features = ["full"] }
tokio-tungstenite = { version = "0.21", features = ["native-tls"] }
futures-util = "0.3"
xcap = "0.0.13"
cpal = "0.15"
image = { version = "0.25", features = ["jpeg"] }
base64 = "0.22"
```

---

## 3.2 — screen_capture.rs

**File:** `apps/desktop/src-tauri/src/screen_capture.rs`

```rust
use xcap::Monitor;
use image::ImageOutputFormat;
use base64::{Engine, engine::general_purpose};

#[tauri::command]
pub fn capture_screen() -> Result<String, String> {
    let monitors = Monitor::all().map_err(|e| e.to_string())?;
    let primary = monitors.into_iter().find(|m| m.is_primary()).ok_or("No primary monitor")?;
    let img = primary.capture_image().map_err(|e| e.to_string())?;

    // Resize to max 1280px wide to reduce bandwidth
    let resized = if img.width() > 1280 {
        image::imageops::resize(&img, 1280, 1280 * img.height() / img.width(), image::imageops::FilterType::Lanczos3)
    } else { img };

    let mut buf = std::io::Cursor::new(Vec::new());
    resized.write_to(&mut buf, ImageOutputFormat::Jpeg(60)).map_err(|e| e.to_string())?;
    Ok(general_purpose::STANDARD.encode(buf.into_inner()))
}
```

---

## 3.3 — audio.rs

**File:** `apps/desktop/src-tauri/src/audio.rs`

```rust
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::{Arc, Mutex};

pub struct AudioState {
    pub mic_chunks: Arc<Mutex<Vec<Vec<u8>>>>,
    _stream: cpal::Stream,
}

impl AudioState {
    pub fn start_capture() -> Result<Self, String> {
        let host = cpal::default_host();
        let device = host.default_input_device().ok_or("No mic found")?;
        let config = cpal::StreamConfig { channels: 1, sample_rate: cpal::SampleRate(16000), buffer_size: cpal::BufferSize::Fixed(1600) };
        let chunks = Arc::new(Mutex::new(Vec::<Vec<u8>>::new()));
        let chunks_w = Arc::clone(&chunks);
        let stream = device.build_input_stream(&config,
            move |data: &[i16], _| {
                let bytes: Vec<u8> = data.iter().flat_map(|s| s.to_le_bytes()).collect();
                chunks_w.lock().unwrap().push(bytes);
            },
            |e| eprintln!("Audio error: {e}"), None
        ).map_err(|e| e.to_string())?;
        stream.play().map_err(|e| e.to_string())?;
        Ok(Self { mic_chunks: chunks, _stream: stream })
    }

    pub fn drain(&self) -> Vec<Vec<u8>> {
        std::mem::take(&mut *self.mic_chunks.lock().unwrap())
    }
}
```

---

## 3.4 — gemini_live.rs

**File:** `apps/desktop/src-tauri/src/gemini_live.rs`

Key behaviours (based on `_python_reference/humphi/gemini_live.py`):
- WebSocket to `wss://generativelanguage.googleapis.com/ws/...?key={GEMINI_API_KEY}`
- Setup message: model `gemini-2.5-flash`, response modalities `AUDIO + TEXT`, voice `Aoede`
- Send loop: mic audio chunks every 100ms + screen JPEG every 1s
- Receive loop: text parts → emit `gemini_text` Tauri event, audio parts → emit `gemini_audio` event
- Auto-reset after 50 turns or 15 minutes (context handoff message sent before reset)

```rust
use tokio_tungstenite::connect_async;
use futures_util::{SinkExt, StreamExt};

static LIVE_RUNNING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

#[tauri::command]
pub async fn start_live_session(api_key: String, app_handle: tauri::AppHandle) -> Result<(), String> {
    LIVE_RUNNING.store(true, std::sync::atomic::Ordering::SeqCst);
    let url = format!("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={api_key}");
    let (ws, _) = connect_async(&url).await.map_err(|e| e.to_string())?;
    let (mut write, mut read) = ws.split();

    // Setup
    write.send(tokio_tungstenite::tungstenite::Message::Text(serde_json::json!({
        "setup": {
            "model": "models/gemini-2.5-flash",
            "generationConfig": { "responseModalities": ["AUDIO","TEXT"], "speechConfig": { "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "Aoede" } } } },
            "systemInstruction": { "parts": [{ "text": SYSTEM_PROMPT }] }
        }
    }).to_string())).await.map_err(|e| e.to_string())?;

    // Send loop
    let app2 = app_handle.clone();
    tokio::spawn(async move {
        let audio = crate::audio::AudioState::start_capture().unwrap();
        let mut screen_tick = tokio::time::interval(std::time::Duration::from_secs(1));
        let mut turn_count = 0u32;
        let start = std::time::Instant::now();

        while LIVE_RUNNING.load(std::sync::atomic::Ordering::SeqCst) {
            tokio::select! {
                _ = screen_tick.tick() => {
                    if let Ok(frame) = crate::screen_capture::capture_screen() {
                        let _ = write.send(tokio_tungstenite::tungstenite::Message::Text(serde_json::json!({
                            "realtimeInput": { "mediaChunks": [{ "mimeType": "image/jpeg", "data": frame }] }
                        }).to_string())).await;
                    }
                }
                _ = tokio::time::sleep(std::time::Duration::from_millis(100)) => {
                    for chunk in audio.drain() {
                        let b64 = base64::engine::general_purpose::STANDARD.encode(&chunk);
                        let _ = write.send(tokio_tungstenite::tungstenite::Message::Text(serde_json::json!({
                            "realtimeInput": { "mediaChunks": [{ "mimeType": "audio/pcm;rate=16000", "data": b64 }] }
                        }).to_string())).await;
                    }
                    turn_count += 1;
                    if turn_count >= 50 || start.elapsed().as_secs() >= 900 {
                        app2.emit("gemini_session_reset", ()).ok();
                        LIVE_RUNNING.store(false, std::sync::atomic::Ordering::SeqCst);
                    }
                }
            }
        }
    });

    // Receive loop
    tokio::spawn(async move {
        while let Some(Ok(tokio_tungstenite::tungstenite::Message::Text(text))) = read.next().await {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&text) {
                if let Some(parts) = val.pointer("/serverContent/modelTurn/parts").and_then(|p| p.as_array()) {
                    for part in parts {
                        if let Some(t) = part.get("text").and_then(|t| t.as_str()) {
                            app_handle.emit("gemini_text", t).ok();
                        }
                        if let Some(data) = part.pointer("/inlineData/data").and_then(|d| d.as_str()) {
                            app_handle.emit("gemini_audio", data).ok();
                        }
                    }
                }
            }
        }
    });

    Ok(())
}

#[tauri::command]
pub fn stop_live_session() {
    LIVE_RUNNING.store(false, std::sync::atomic::Ordering::SeqCst);
}

const SYSTEM_PROMPT: &str = "You are Humphi, a friendly AI desktop assistant watching the user's screen. You can see what they're doing and guide them through tasks step by step. Be concise and specific — tell them exactly what to click or type.";
```

---

## 3.5 — Register Rust Commands

**File:** `apps/desktop/src-tauri/src/lib.rs`

```rust
mod screen_capture;
mod audio;
mod gemini_live;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            mcp_tool_call,
            screen_capture::capture_screen,
            gemini_live::start_live_session,
            gemini_live::stop_live_session,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

---

## 3.6 — Live Mode UI

**File:** `apps/desktop/src/pages/LivePage.tsx`

```tsx
export function LivePage() {
  const { getToken } = useAuth()
  const [status, setStatus] = useState<'idle' | 'connecting' | 'live' | 'ended'>('idle')
  const [transcript, setTranscript] = useState<string[]>([])

  useEffect(() => {
    const unlisten1 = listen('gemini_text', (e) => setTranscript(p => [...p, e.payload as string]))
    const unlisten2 = listen('gemini_session_reset', () => setStatus('ended'))
    return () => { unlisten1.then(f => f()); unlisten2.then(f => f()) }
  }, [])

  async function startSession() {
    setStatus('connecting')
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY
    await invoke('start_live_session', { apiKey })
    setStatus('live')
  }

  async function endSession() {
    await invoke('stop_live_session')
    setStatus('ended')
  }

  return (
    <div className="flex flex-col h-full bg-[#0a0c10] p-6">
      <div className="flex items-center justify-between mb-4">
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          status === 'live' ? 'bg-green-500/20 text-green-400' :
          status === 'connecting' ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-gray-500/20 text-gray-400'
        }`}>{status.toUpperCase()}</span>
        {status === 'idle' && <button onClick={startSession} className="btn-primary">Start Live Session</button>}
        {status === 'live' && <button onClick={endSession} className="btn-danger">End Session</button>}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {transcript.map((t, i) => <p key={i} className="text-[#e2e8f8] text-sm">{t}</p>)}
      </div>
    </div>
  )
}
```

Add "Live" tab to `ChatPage.tsx` header next to "Chat".

**Plan gate:** If `user.plan === 'free'`, show upgrade prompt instead of live session button.

---

## 3.7 — v0.2 Pre-Ship Checklist
- [ ] "Help me fix this Excel formula" → Gemini sees screen, talks through fix
- [ ] Audio plays back through speakers
- [ ] Session auto-resets at 50 turns with context handoff message
- [ ] Live tab gated behind Pro plan check
- [ ] Gemini API key stored securely (not in code — use `tauri-plugin-store`)
- [ ] End session button posts telemetry

---

---

# Phase 4 — Week 7-8: Composio Connectors + Stripe Billing (v1.0)
**Ship target:** "Summarise my unread emails", Stripe charging £10/month. Start selling to small businesses.

---

## 4.1 — Stripe Setup

Create products in Stripe dashboard:
- **Free** — £0 — 100 calls/day, chat only
- **Pro** — £10/month — unlimited calls, live mode, connectors
- **Corporate** — £30/user/month — everything + admin dashboard, audit logs

**File:** `apps/api/src/lib/stripe.ts`

```typescript
import Stripe from 'stripe'
export const stripe = (env: Env) => new Stripe(env.STRIPE_SECRET_KEY)

export const PLAN_PRICE_IDS: Record<string, string> = {
  pro:       process.env.STRIPE_PRICE_PRO!,
  corporate: process.env.STRIPE_PRICE_CORPORATE!,
}
```

---

## 4.2 — Billing Domain

**File:** `apps/api/src/domains/billing/routes.ts`

```typescript
// POST /billing/checkout
billingRouter.post('/checkout', requireAuth, async (c) => {
  const userId = c.get('userId')
  const { plan } = await c.req.json()
  const user = await getUserById(c.env, userId)
  const s = await stripe(c.env).checkout.sessions.create({
    customer_email: user.email,
    mode: 'subscription',
    line_items: [{ price: PLAN_PRICE_IDS[plan], quantity: 1 }],
    success_url: `${c.env.WEB_URL}/dashboard/billing?success=true`,
    cancel_url: `${c.env.WEB_URL}/dashboard/billing`,
    metadata: { userId },
  })
  return c.json({ url: s.url })
})

// POST /billing/portal
billingRouter.post('/portal', requireAuth, async (c) => {
  const userId = c.get('userId')
  const user = await getUserById(c.env, userId)
  const s = await stripe(c.env).billingPortal.sessions.create({
    customer: user.stripeCustomerId!,
    return_url: `${c.env.WEB_URL}/dashboard/billing`,
  })
  return c.json({ url: s.url })
})

// POST /billing/webhook
billingRouter.post('/webhook', async (c) => {
  const sig = c.req.header('stripe-signature')!
  const body = await c.req.text()
  const event = await stripe(c.env).webhooks.constructEventAsync(body, sig, c.env.STRIPE_WEBHOOK_SECRET)

  switch (event.type) {
    case 'checkout.session.completed': {
      const s = event.data.object
      await db(c.env).update(users).set({
        plan: s.metadata?.plan ?? 'pro',
        stripeCustomerId: s.customer as string,
        stripeSubscriptionId: s.subscription as string,
      }).where(eq(users.id, s.metadata!.userId))
      await redis(c.env).del(`plan:${s.metadata!.userId}`)  // bust cache
      await sendEmail(c.env, s.metadata!.userId, 'PLAN_UPGRADED', { plan: 'Pro' })
      break
    }
    case 'customer.subscription.deleted': {
      const userId = await getUserIdByStripeCustomer(c.env, event.data.object.customer as string)
      await db(c.env).update(users).set({ plan: 'free' }).where(eq(users.id, userId))
      await redis(c.env).del(`plan:${userId}`)
      await sendEmail(c.env, userId, 'PLAN_DOWNGRADED', {})
      break
    }
    case 'invoice.payment_failed': {
      const userId = await getUserIdByStripeCustomer(c.env, event.data.object.customer as string)
      await sendEmail(c.env, userId, 'PAYMENT_FAILED', {})
      break
    }
  }
  return c.json({ received: true })
})
```

---

## 4.3 — Billing Page (Web + Desktop)

**`apps/web/src/app/dashboard/billing/page.tsx`**
**`apps/desktop/src/pages/BillingPage.tsx`**

Same layout on both:
- Current plan card with feature list
- Usage bar: calls today / daily limit
- Upgrade buttons → POST `/billing/checkout` → redirect to Stripe Checkout URL
- "Manage Subscription" (paid users) → POST `/billing/portal` → Stripe portal
- Next renewal date, last 3 invoices

---

## 4.4 — Brevo Email

**File:** `apps/api/src/lib/brevo.ts`

```typescript
export async function sendEmail(env: Env, userId: string, templateName: keyof typeof EMAIL_TEMPLATES, params: Record<string, unknown>) {
  const user = await getUserById(env, userId)
  await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: { 'api-key': env.BREVO_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to: [{ email: user.email, name: user.name }],
      templateId: EMAIL_TEMPLATES[templateName],
      params: { name: user.name, ...params },
    }),
  })
}

export const EMAIL_TEMPLATES = {
  WELCOME:            1,
  USAGE_80_PERCENT:   2,
  USAGE_LIMIT_REACHED:3,
  PLAN_UPGRADED:      4,
  PLAN_DOWNGRADED:    5,
  PAYMENT_FAILED:     6,
  WEEKLY_REPORT:      7,
  BILLING_REMINDER:   8,
}
```

Send welcome email from `POST /auth/clerk-webhook` on `user.created`.

---

## 4.5 — Inngest Jobs

**File:** `apps/api/src/lib/inngest.ts`

All scheduled and event-driven jobs live here. Inngest calls back into `POST /api/inngest` on the Worker.

```typescript
import { Inngest } from 'inngest'
import { serve } from 'inngest/hono'

export const inngest = new Inngest({ id: 'humphi-ai' })

// Cron: session cleanup every hour
export const sessionCleanupFn = inngest.createFunction(
  { id: 'session-cleanup', retries: 2 },
  { cron: '0 * * * *' },
  async ({ step }) => {
    await step.run('cleanup', async () => {
      const cutoff = new Date(Date.now() - 2 * 60 * 60 * 1000)
      await db.update(sessions).set({ endedAt: new Date(), summary: 'Auto-closed' })
        .where(and(isNull(sessions.endedAt), lt(sessions.startedAt, cutoff)))
    })
  }
)

// Cron: weekly report fan-out — Sunday 8am
export const weeklyReportFn = inngest.createFunction(
  { id: 'weekly-report', retries: 1 },
  { cron: '0 8 * * 0' },
  async ({ step }) => {
    const allUsers = await step.run('get-users', () => db.select({ id: users.id, email: users.email, name: users.name }).from(users))
    // Fan-out: one event per user, each retried independently
    await inngest.send(allUsers.map(u => ({ name: 'report/weekly', data: { userId: u.id } })))
  }
)

export const weeklyReportEmailFn = inngest.createFunction(
  { id: 'weekly-report-email', retries: 3 },
  { event: 'report/weekly' },
  async ({ event, step }) => {
    await step.run('send', () => sendWeeklyReportEmail(event.data.userId))
  }
)

// Event: usage alert — triggered inline from telemetry route
export const usageAlertFn = inngest.createFunction(
  { id: 'usage-alert', retries: 3 },
  { event: 'usage/alert' },
  async ({ event, step }) => {
    await step.run('send-email', () => sendUsageAlertEmail(event.data))
  }
)

// Cron: billing reminders — 1st of month
export const billingReminderFn = inngest.createFunction(
  { id: 'billing-reminder', retries: 1 },
  { cron: '0 9 1 * *' },
  async ({ step }) => {
    const freeUsers = await step.run('get-users', () => db.select({ id: users.id }).from(users).where(eq(users.plan, 'free')))
    await inngest.send(freeUsers.map(u => ({ name: 'billing/reminder', data: { userId: u.id } })))
  }
)

export const allInngestFunctions = [sessionCleanupFn, weeklyReportFn, weeklyReportEmailFn, usageAlertFn, billingReminderFn]
```

Triggering from the telemetry route (event-driven, no cron):
```typescript
// In telemetry/routes.ts — fires the moment threshold is crossed
if (threshold) {
  await inngest.send({ name: 'usage/alert', data: { userId, usage, limit, threshold } })
}
```

---

## 4.6 — Composio Gmail Connector

**File:** `apps/api/src/lib/composio.ts`

```typescript
import { CloudflareToolSet } from 'composio-core'

export function composio(env: Env, userId: string) {
  return new CloudflareToolSet({ apiKey: env.COMPOSIO_API_KEY, entityId: userId })
}

export async function getToolsForUser(env: Env, userId: string, apps: string[]) {
  if (!apps.length) return []
  return composio(env, userId).getTools({ apps })
}

export async function executeComposioTool(env: Env, userId: string, toolName: string, args: unknown) {
  return composio(env, userId).executeAction(toolName, args as Record<string, unknown>)
}
```

**File:** `apps/api/src/domains/connectors/routes.ts`

```typescript
// GET /connectors
connectorsRouter.get('/', requireAuth, async (c) => {
  const prefs = await getPreferences(c.env, c.get('userId'))
  return c.json({ connectors: buildConnectorList(prefs.connectedApps) })
})

// POST /connectors/gmail/connect
connectorsRouter.post('/:app/connect', requireAuth, async (c) => {
  const userId = c.get('userId')
  const app = c.req.param('app')

  // Gate behind Pro
  const user = await getUserById(c.env, userId)
  if (user.plan === 'free') return c.json({ error: 'Connectors require Pro plan' }, 403)

  const cs = composio(c.env, userId)
  const { redirectUrl } = await cs.getExpectedParamsForUser({ app, entityId: userId })
  return c.json({ redirectUrl })
})

// DELETE /connectors/:app
connectorsRouter.delete('/:app', requireAuth, async (c) => {
  const { userId, app } = { userId: c.get('userId'), app: c.req.param('app') }
  await composio(c.env, userId).entity.disableConnectedAccount({ appName: app })
  await removeConnectedApp(c.env, userId, app)
  return c.json({ ok: true })
})
```

**Gmail tools available after connection:**
`GMAIL_SEND_EMAIL`, `GMAIL_FETCH_EMAILS`, `GMAIL_CREATE_EMAIL_DRAFT`, `GMAIL_LIST_THREADS`

---

## 4.7 — Connectors Page (Web + Desktop)

Both show the same connector cards. State comes from `GET /connectors`.

Each card:
- App icon + name
- Status: Connected (shows account email + connected date) / Not connected
- Connect button → redirects to OAuth URL from Composio
- Disconnect button (if connected)
- Pro gate: free users see "Requires Pro" badge

Connectors to show in v1.0: **Gmail** (connected), **Outlook** (coming soon), **QuickBooks** (coming soon), **Opera PMS** (enterprise)

---

## 4.8 — v1.0 Pre-Ship Checklist
- [ ] Gmail OAuth connects and "summarise my unread emails" works
- [ ] Stripe Pro plan at £10/month — checkout flow works end-to-end
- [ ] Webhook correctly upgrades user plan in DB + busts Redis cache
- [ ] Payment failure email fires via Brevo
- [ ] Free users hit 100 call/day limit and get the limit-reached email
- [ ] Weekly report emails send on Sunday
- [ ] Billing page on both web and desktop
- [ ] Plan badge shows in sidebar on desktop

---

---

# Phase 5 — Week 9+: Growth Features

## 5.1 — Outlook Connector (via Composio)

Same pattern as Gmail. Tools: `MICROSOFT_OUTLOOK_SEND_EMAIL`, `MICROSOFT_OUTLOOK_LIST_EMAILS`, `MICROSOFT_OUTLOOK_CREATE_CALENDAR_EVENT`.

---

## 5.2 — QuickBooks Connector

**Check Composio catalog first.** If Composio supports `QUICKBOOKS`:
- Same OAuth pattern as Gmail

**If not — Custom MCP Server:**
```
apps/api/src/domains/connectors/quickbooks-mcp/
├── server.ts     # @modelcontextprotocol/sdk stdio server
├── client.ts     # node-quickbooks OAuth + API calls
└── tools.ts      # create_invoice, list_invoices, get_customer, create_payment, get_report
```

OAuth via Intuit Developer Portal (Authorization Code flow). Tokens stored in `preferences.connectedApps.quickbooks`.

---

## 5.3 — Opera PMS Connector (Enterprise)

**Custom MCP Server** (Composio almost certainly won't have this):
```
apps/api/src/domains/connectors/opera-mcp/
├── server.ts     # MCP stdio server
├── client.ts     # Oracle OHIP REST API v2 (OAuth 2.0 client credentials)
└── tools.ts      # get_reservation, check_in_guest, check_out_guest, get_room_status, post_charge, get_folio
```

Credentials (OHIP `client_id` + `client_secret`) stored in `preferences.connectedApps.opera_pms`. Enterprise-only — gated behind Corporate plan.

---

## 5.4 — Admin Dashboard (IT Teams)

**`apps/web/src/app/admin/`** — real Drizzle queries replacing all mocks.

```typescript
// GET /admin/stats?range=today|7d|30d|all
adminRouter.get('/stats', requireAuth, requireAdmin, async (c) => {
  const range = c.req.query('range') ?? 'today'
  const from = rangeToDate(range)
  const [userCount, callCount, costSum, activeSessions] = await Promise.all([
    db(c.env).select({ count: count() }).from(users),
    db(c.env).select({ count: count() }).from(apiCalls).where(gte(apiCalls.timestamp, from)),
    db(c.env).select({ sum: sum(apiCalls.costUsd) }).from(apiCalls).where(gte(apiCalls.timestamp, from)),
    db(c.env).select({ count: count() }).from(sessions).where(isNull(sessions.endedAt)),
  ])
  return c.json({ userCount: userCount[0].count, callCount: callCount[0].count, costSum: costSum[0].sum, activeSessions: activeSessions[0].count })
})

// GET /admin/users?search=&plan=&page=
adminRouter.get('/users', requireAuth, requireAdmin, async (c) => {
  const { search, plan, page = '1' } = c.req.query()
  const conditions = [
    search ? or(ilike(users.email, `%${search}%`), ilike(users.name, `%${search}%`)) : undefined,
    plan ? eq(users.plan, plan) : undefined,
  ].filter(Boolean)
  const rows = await db(c.env).select().from(users).where(and(...conditions)).limit(20).offset((Number(page) - 1) * 20)
  return c.json({ users: rows })
})
```

---

## 5.5 — Windows MCP

When Microsoft ships the official Windows MCP server: slot it in as a new connector in the `buildToolList` function. It will surface Windows-native tools (shell, settings, calendar, etc.) that can run alongside the existing Rust desktop commander tools. No architecture change needed — just add it to the tool router.

---

## 5.6 — Shared UI Package

**`packages/ui/`** — extract components used in both web and desktop to avoid duplication:
- `ChatMessage` — single message bubble with tool call display
- `MetricCard` — dashboard stat card
- `ConnectorCard` — OAuth connect/disconnect UI
- `PlanBadge` — free/pro/corporate
- `UsageBar` — progress bar

Both apps import from `@humphi/ui`.

---

---

# Inngest Decision Guide

| Need | How |
|------|-----|
| Run at a fixed time | `inngest.createFunction({ id }, { cron: '...' }, handler)` |
| Fan out to N users | Cron function calls `inngest.send([...events])` — each event runs independently with its own retries |
| Triggered by user action | `inngest.send({ name: 'event/name', data })` from inside any Hono route |
| Delayed task | `await step.sleep('3 days')` inside a function |
| Webhook retry | Stripe/Composio handle natively — no Inngest needed |

---

# Environment Variables

```bash
# Clerk
CLERK_SECRET_KEY=
VITE_CLERK_PUBLISHABLE_KEY=            # desktop
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=     # web

# Neon
NEON_DATABASE_URL=

# Upstash
UPSTASH_REDIS_URL=
UPSTASH_REDIS_TOKEN=
INNGEST_SIGNING_KEY=
INNGEST_EVENT_KEY=

# Stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_PRO=
STRIPE_PRICE_CORPORATE=
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=

# Brevo
BREVO_API_KEY=

# Cloudflare
CF_ACCOUNT_ID=
CF_GATEWAY_NAME=
CF_AIG_TOKEN=

# AI
OPENROUTER_API_KEY=
VITE_GEMINI_API_KEY=                   # desktop only — for Live mode

# Composio
COMPOSIO_API_KEY=

# Custom MCP (added when connectors are built)
QUICKBOOKS_CLIENT_ID=
QUICKBOOKS_CLIENT_SECRET=
OHIP_HOST=
OHIP_CLIENT_ID=
OHIP_CLIENT_SECRET=

# App URLs
WEB_URL=https://humphi.ai
API_URL=https://api.humphi.ai          # Cloudflare Worker URL
```

---

# Phase Timeline Summary

| Phase | Weeks | Ship | Key Deliverables |
|-------|-------|------|-----------------|
| **1** | 1-2 | Internal | Monorepo · Hono API · Clerk on desktop + web · Claude via CF Gateway · Neon chat history |
| **2** | 3-4 | v0.1 → 5 users | DesktopCommanderMCP full tool set · "Open Excel" · "Read this file" |
| **3** | 5-6 | v0.2 → killer feature | Gemini Live (screen + voice) · "Help me fix this formula" |
| **4** | 7-8 | v1.0 → sell | Gmail via Composio · Stripe £10/mo · Brevo emails · Inngest jobs |
| **5** | 9+  | Growth | Outlook · QuickBooks · Opera PMS · Admin dashboard · Windows MCP |
