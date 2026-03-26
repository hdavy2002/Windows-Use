# Humphi AI — Master Implementation Plan v2
## Complete Rebuild: Tauri + MCP + Clerk + Neon + mem0 + Composio

---

## Project Identity
- **Product**: Humphi AI — AI Desktop Operator
- **Tagline**: AI Eyes, User Hands
- **Languages**: TypeScript + Rust only. NO PYTHON. Zero Python dependencies.
- **Desktop App**: Tauri (Rust backend + React + shadcn/ui + Radix UI frontend)
- **Web Dashboard**: Next.js + shadcn/ui (Vercel)
- **Auth**: Clerk (registration + login, both web and desktop)
- **Database**: Neon PostgreSQL (per-user isolated schema)
- **Memory**: mem0 (per-user, backed by Neon)
- **Local MCP**: DesktopCommanderMCP (runs locally on user's machine, Node.js)
- **Cloud MCPs**: Gmail, Calendar, Drive (future)
- **AI Chat**: OpenRouter (multiple models)
- **AI Live**: Gemini Live API (WebSocket from Rust backend — screen capture via xcap, audio via cpal)
- **AI Gateway**: Cloudflare AI Gateway (provider switching, logging, retries, caching)

### Why No Python
- Users don't need Python installed (massive UX win for distribution)
- One install, no dependencies — just the Tauri .exe/.msi
- Screen capture in Rust (xcap crate) is faster than PIL ImageGrab
- Audio in Rust (cpal crate) is lower latency than sounddevice
- WebSocket to Gemini works from Rust (tokio-tungstenite)
- Gemini Live code is only ~294 lines — straightforward rewrite
- Single runtime = simpler builds, CI/CD, and debugging

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  TAURI DESKTOP APP (Rust + React + shadcn/ui)               │
│  ├── Chat UI (login required via Clerk)                     │
│  ├── Go Live (Gemini screen share + voice)                  │
│  └── MCP Client → connects to DesktopCommanderMCP (local)   │
└─────────────────┬───────────────────────────────────────────┘
                  │ HTTPS
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  CLOUDFLARE AI GATEWAY                                       │
│  ├── Provider switching (OpenRouter, Gemini, etc.)           │
│  ├── Logging + analytics                                     │
│  ├── Retries on failure                                      │
│  ├── Caching (semantic + exact)                              │
│  └── Rate limiting                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM PROVIDERS (hidden from client)                          │
│  ├── OpenRouter → GPT-4.1, MiniMax, Llama, etc.             │
│  └── Google → Gemini Live (direct WebSocket for live mode)   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  NEON DATABASE (per-user schema)                             │
│  ├── api_calls (full token breakdown per call)               │
│  ├── sessions                                                │
│  ├── mem0_memories (per-user memory)                         │
│  └── preferences                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  WEB DASHBOARD (Next.js + shadcn/ui, Vercel)                 │
│  ├── User dashboard (usage, history, settings)               │
│  ├── Admin dashboard (all users, analytics, drill-down)      │
│  └── Clerk auth (same as desktop)                            │
└─────────────────────────────────────────────────────────────┘

---

## Key Decisions

### Intent Router: REMOVED
The Cloudflare D1 Worker intent router is deleted. With DesktopCommanderMCP,
the AI model gets structured tools via function calling and decides which to use.
The AI IS the router. No keyword matching, no workflow caching, no classification calls.

### DesktopCommanderMCP: LOCAL
Runs as a local Node.js MCP server on the user's machine. The Tauri app connects
to it as an MCP client. It handles ALL local computer operations: terminal, files,
processes, code execution, Excel/PDF/DOCX. No more hardcoded PowerShell commands.

### Cloudflare AI Gateway: REPLACES Bifrost
Used for provider switching, logging, retries, caching. NOT for intent routing.
The desktop app calls AI through the gateway. Keys stay server-side.

### Local Logging: REMOVED
No more ~/.humphi/telemetry.jsonl, session_summaries.jsonl, memory.json.
ALL telemetry goes to the user's Neon DB via API. Admin dashboard reads from Neon.

### mcp2cli: EVALUATED AND REJECTED
mcp2cli (github.com/knowsuchagency/mcp2cli) turns MCP servers into CLIs to save
96-99% of tokens wasted on tool schemas. While the token savings are real, we rejected it because:
1. It's Python-only (pip install). We are a zero-Python stack.
2. CLI approach adds subprocess latency per tool call.
3. We connect to DesktopCommanderMCP directly via MCP stdio — zero overhead.
4. We'll implement our own lean tool injection: only send 5-6 relevant tool schemas
   per turn based on conversation context, not all 20. Same lazy-loading benefit.
5. Anthropic Tool Search (defer_loading: true) achieves similar savings natively.

### Composio: YES — Cloud MCP Integrations
Composio (composio.dev) provides 300+ app integrations via MCP with managed OAuth.
We use Composio for ALL cloud integrations (Gmail, Drive, Calendar, Slack, etc.).
- They handle OAuth, token refresh, scopes — we don't build any connectors.
- MCP-native: generates per-user MCP URLs our AI calls directly.
- Tool Router: auto-discovers which toolkit matches the user's request.
- Per-user sessions via composio.create(user_id=clerk_user_id).
- "Connectors" page in user dashboard shows available apps with connect/disconnect.
- Composio SDK: @composio/core (TypeScript) — fits our stack perfectly.

### Token Optimization Strategy (replaces mcp2cli)
Instead of mcp2cli, we implement our own lean approach:
1. DesktopCommander tools: only inject schemas for tools relevant to current task.
   AI sees 5-6 tools per turn, not 20. Context-aware filtering in our API layer.
2. Composio tools: Tool Router handles discovery. Only matched tools enter context.
3. System prompt: compressed to ~80 tokens. No verbose instructions.
4. History: last 2 turns + 50-token mem0 summary. No full conversation replay.
5. Result: estimated ~500-800 tokens/turn for tools, vs 3,000+ without optimization.

---

## What Gets DELETED from Current Codebase

| Delete | Reason |
|--------|--------|
| `humphi/capabilities/*.json` (all 11 files) | Replaced by MCP tools |
| `humphi/capabilities/__init__.py` | Replaced by MCP tools |
| `humphi/memory.py` | Replaced by mem0 + Neon |
| `humphi-knowledge/` (entire CF Worker) | Intent router removed |
| All `ALLOWED_CMDS`, `ACTION_MAP`, `run_cmd()` | MCP handles execution |
| All `parse_actions()`, `execute_action()` | MCP handles execution |
| All `check_direct_command()`, `match_workflow()` | MCP handles everything |
| All `learn_workflow()` | No more workflow caching |
| All local JSON logging | Neon DB instead |
| `classify_intent()`, `ROUTER_MODEL` | AI decides via tool use |
| `INJECTION_PATTERNS`, `check_injection()` | Keep but move to API layer |
| `tests/` (all current tests) | Rewrite for new architecture |
| `test_match.py` | Tests removed features |
| `.wrangler/` | D1 worker gone |
| `.pytest_cache/` | Cleanup |

## What Gets KEPT (as reference for Rust rewrite, then deleted)

| Python File | Purpose | Rewritten To |
|-------------|---------|-------------|
| `humphi/gemini_live.py` | Gemini WebSocket + 7 cost controls | `src-tauri/src/gemini_live.rs` |
| `humphi/screen_capture.py` | Adaptive FPS, colour-aware capture | `src-tauri/src/screen_capture.rs` |
| `humphi/audio.py` | Mic + speaker PCM | `src-tauri/src/audio.rs` |
| `humphi/overlay.py` | LIVE ticker | React component in frontend |

These Python files are kept ONLY as reference during Phase 5 rewrite, then deleted.
After Phase 5, the entire `humphi/` directory is removed. Zero Python in the final app.

### Files That Are Gone Immediately (Phase 1 Cleanup)
| Delete | Reason |
|--------|--------|
| `main_humphi.py` | Entire app rewritten in Tauri |
| `pyproject.toml` | No more Python |
| `humphi/__init__.py` | No more Python package |
| `humphi/capabilities/` (entire dir) | MCP replaces capabilities |
| `humphi/memory.py` | mem0 + Neon replaces this |
| `humphi-knowledge/` (entire dir) | D1 Worker deleted |
| `humphi-complete.html` | Old docs |
| `assets/` (pywebview HTML/JS/CSS) | Tauri React replaces this |
| `tests/`, `test_match.py` | Rewrite for new architecture |
| `.wrangler/`, `.pytest_cache/` | Cleanup |
| `__pycache__/` (all) | No more Python |


---

## PHASE 1: Foundation — Auth + Database + Cleanup
**Timeline: Week 1-2**
**Goal: Users can register, log in, and have a database. Codebase stripped clean.**

### 1A. Web Dashboard (Next.js + shadcn/ui on Vercel)
- [ ] Init Next.js project with TypeScript
- [ ] Install shadcn/ui + Radix UI + Tailwind
- [ ] Integrate Clerk for auth (sign up, sign in, Google OAuth)
- [ ] Create layout: sidebar + main content area
- [ ] Pages: `/login`, `/dashboard`, `/dashboard/settings`
- [ ] Dark theme matching our color palette (#1a1b26, #e1e5f2, #7aa2f7)

### 1B. Neon Database
- [ ] Set up Neon project
- [ ] Schema design:
  ```sql
  -- Per-user schema or shared with user_id FK
  CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- Clerk user ID
    email TEXT NOT NULL,
    name TEXT,
    plan TEXT DEFAULT 'free',       -- free/pro/corporate
    created_at TIMESTAMPTZ DEFAULT NOW()
  );

  CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    summary TEXT,
    mode TEXT DEFAULT 'chat'        -- chat/live
  );

  CREATE TABLE api_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id),
    session_id UUID REFERENCES sessions(id),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    model TEXT NOT NULL,
    intent TEXT,
    -- Token breakdown
    prompt_tokens INT,
    completion_tokens INT,
    total_tokens INT,
    memory_tokens_injected INT,
    system_tokens INT,
    -- Cost
    cost_usd NUMERIC(10,6),
    latency_ms INT,
    -- Metadata
    was_cache_hit BOOLEAN DEFAULT FALSE,
    capability_used TEXT,
    mcp_tools_called TEXT[]        -- which MCP tools were invoked
  );

  CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id),
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```
- [ ] API routes: POST `/api/telemetry/log`, GET `/api/telemetry/user/:id`
- [ ] Clerk webhook to create user row on signup

### 1C. Codebase Cleanup
- [ ] Delete all capability JSONs and loader
- [ ] Delete humphi/memory.py
- [ ] Delete humphi-knowledge/ (entire CF Worker dir)
- [ ] Delete all hardcoded PowerShell (ALLOWED_CMDS, ACTION_MAP, run_cmd, etc.)
- [ ] Delete all intent routing (classify_intent, check_direct_command, etc.)
- [ ] Delete all local JSON logging
- [ ] Delete tests/ and test_match.py
- [ ] Delete .wrangler/, .pytest_cache/
- [ ] Keep: gemini_live.py, screen_capture.py, audio.py, overlay.py
- [ ] Update .gitignore (add .env, node_modules, __pycache__)


---

## PHASE 2: Tauri Desktop App + DesktopCommanderMCP
**Timeline: Week 2-4**
**Goal: Sexy Tauri app with login, chat, and MCP-powered local execution.**

### 2A. Tauri App Setup
- [ ] Init Tauri project (Rust backend + React frontend)
- [ ] shadcn/ui + Radix UI + Tailwind in the React frontend
- [ ] Dark theme (#1a1b26 background, #e1e5f2 text, #7aa2f7 accent)
- [ ] Login screen (Clerk embedded auth — like Desktop Commander's welcome)
- [ ] After login: chat interface with sidebar
- [ ] Sidebar: Chat, Files (folder browser), Settings, Account
- [ ] Chat: streaming responses, typing indicator (●●●)
- [ ] Go Live button (red, prominent)
- [ ] Mic toggle button (off by default)
- [ ] Quick-action chips (context-aware based on system state)

### 2B. DesktopCommanderMCP Integration
- [ ] Install DesktopCommanderMCP: `npx @wonderwhy-er/desktop-commander@latest`
- [ ] Connect Tauri app as MCP client (via MCP TypeScript SDK)
- [ ] Expose DC tools to AI as function definitions:
  - `execute_command` — run terminal commands
  - `read_file` / `write_file` — file operations
  - `list_directory` — browse filesystem
  - `edit_block` — surgical file edits
  - `start_process` / `interact_with_process` — interactive REPLs
  - `get_file_info` — file metadata
  - `start_search` — search files/content
  - `move_file` — move/rename
- [ ] System prompt becomes tool-use focused:
  ```
  You are Humphi, an AI desktop assistant. You have Desktop Commander tools
  to execute commands, manage files, and control processes on the user's PC.
  Use these tools to help the user. For visual tasks, suggest Go Live mode.
  ```
- [ ] AI decides which tools to call — no intent router needed
- [ ] Safety handled by DC's own blocklist + our Clerk auth layer

### 2C. Chat → AI → MCP Flow
```
User types: "open my downloads folder"
  → AI receives message + available tools
  → AI decides: call execute_command("explorer.exe Downloads")
  → MCP executes locally
  → Result returned to AI
  → AI responds: "Opened your Downloads folder"

User types: "what's eating my CPU?"
  → AI decides: call execute_command("Get-Process | Sort CPU -Desc | Select -First 10")
  → MCP executes, returns process table
  → AI analyzes and responds: "Chrome is using 45% CPU with 12 tabs open..."
```


---

## PHASE 3: mem0 Memory + Telemetry Pipeline
**Timeline: Week 4-5**
**Goal: Per-user memory that persists. Every API call logged to Neon.**

### 3A. mem0 Integration
- [ ] Set up mem0 per user (backed by Neon `memories` table)
- [ ] Before each AI call: fetch relevant memories → inject as context
- [ ] After each AI call: extract new facts → store in mem0
- [ ] Track `memory_tokens_injected` per call
- [ ] Memory types: user preferences, past tasks, skill level, common patterns
- [ ] Memory prompt injection: "User is intermediate. Prefers concise answers. Last task: DNS fix."

### 3B. Telemetry Pipeline
- [ ] Every AI call logs to `api_calls` table via API:
  - timestamp, session_id, model used
  - prompt_tokens, completion_tokens, total_tokens
  - memory_tokens_injected, system_tokens
  - intent (if applicable), capability_used
  - mcp_tools_called (array of tool names invoked)
  - latency_ms, cost_usd, was_cache_hit
- [ ] Tauri app sends telemetry after each AI response
- [ ] Batch send option for offline resilience
- [ ] No local file logging — everything goes to Neon

### 3C. Live Mode Telemetry
- [ ] Track Gemini Live session: start, end, frame_count, turn_count, cost
- [ ] Log to `sessions` table with mode='live'
- [ ] Cost tracking per live session (accumulated token cost)


---

## PHASE 4: Admin Dashboard + User Analytics
**Timeline: Week 5-7**
**Goal: Admin sees all users, drills into per-call token breakdown.**

### 4A. Admin Pages (Next.js + shadcn/ui)
- [ ] `/admin` — overview: total users, total calls, total cost, active sessions
- [ ] `/admin/users` — table of all registered users:
  - Name, email, plan, total calls, total tokens, total cost, last active
  - Click row → go to user detail
- [ ] `/admin/users/[id]` — specific user:
  - Profile info, plan, signup date
  - Usage chart (calls per day, tokens per day)
  - Session history (list of sessions with duration + mode)
  - Total spend, common intents
  - mem0 memory snapshot (what we know about this user)
- [ ] `/admin/users/[id]/calls` — all API calls:
  - Table: timestamp, model, intent, total_tokens, cost, latency
  - Click row → drill into call detail
- [ ] `/admin/users/[id]/calls/[callId]` — single call detail:
  - Full token breakdown: prompt, completion, memory injected, system
  - Model used, intent classified
  - MCP tools called (list)
  - Response time, cost
  - Was it a cache hit?
  - Raw request/response (truncated)

### 4B. User Dashboard
- [ ] `/dashboard` — user's own usage:
  - Calls this month, tokens used, estimated cost
  - Quick stats cards
- [ ] `/dashboard/history` — their session history
- [ ] `/dashboard/settings` — profile, voice preference, connected MCPs
- [ ] `/dashboard/billing` — plan info, top-up (future)


---

## PHASE 5: Gemini Live Mode (Rewritten in Rust + TypeScript)
**Timeline: Week 7-8**
**Goal: Live screen sharing with Gemini, native in Tauri. No Python.**

### 5A. Rewrite Python Modules in Rust
The following Python modules get rewritten as Rust Tauri commands:

| Python Module (DELETE) | Rust Replacement |
|------------------------|-----------------|
| `humphi/gemini_live.py` (294 lines) | `src-tauri/src/gemini_live.rs` — WebSocket via tokio-tungstenite |
| `humphi/screen_capture.py` (184 lines) | `src-tauri/src/screen_capture.rs` — xcap crate for capture |
| `humphi/audio.py` (107 lines) | `src-tauri/src/audio.rs` — cpal crate for mic + speaker |
| `humphi/overlay.py` (64 lines) | React component in frontend (no separate window) |

### 5B. Rust Crates Needed
```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
tokio-tungstenite = "0.21"      # WebSocket to Gemini
xcap = "0.0.11"                  # Screen capture (Windows/Mac/Linux)
cpal = "0.15"                    # Audio capture + playback
image = "0.25"                   # JPEG compression
base64 = "0.22"                  # Frame encoding
serde_json = "1"                 # JSON for Gemini protocol
```

### 5C. Cost Controls (Already Implemented)
1. Session reset every 15 minutes
2. Frame diff (only send when screen changes)
3. Pause video while AI speaks
4. Low resolution (MEDIA_RESOLUTION_LOW)
5. Turn rate tracking
6. Per-session cost cap ($2.00)
7. Smart mic (off by default)

---

## PHASE 6: Cloud MCPs + Cloudflare AI Gateway
**Timeline: Week 8-10**
**Goal: Cloud integrations and AI gateway for production.**

### 6A. Cloudflare AI Gateway
- [ ] Set up CF AI Gateway
- [ ] Route all AI calls through gateway
- [ ] Provider switching (swap models without app update)
- [ ] Logging + analytics (every request tracked)
- [ ] Retries on failure
- [ ] Caching (semantic + exact match)
- [ ] Rate limiting per user
- [ ] API keys stay server-side — app never holds them

### 6B. Cloud MCP Integrations via Composio
- [ ] Install Composio SDK: `npm install @composio/core`
- [ ] Set up Composio account + API key
- [ ] Create "Connectors" page in user dashboard (`/dashboard/connectors`)
  - Grid of app icons: Gmail, Google Drive, Calendar, Slack, Notion, GitHub, etc.
  - Each shows: connected ✅ / not connected ⚪
  - Click to connect → Composio OAuth flow → redirect back → connected
  - Click to disconnect → revoke token
- [ ] Backend: per-user Composio session via `composio.create(user_id=clerk_user_id)`
- [ ] Composio MCP URL stored per user in Neon
- [ ] Chat integration: AI calls Composio MCP endpoint for cloud actions
  - "Summarize my unread emails" → Composio Gmail MCP → returns summaries
  - "Save this to my Drive" → Composio Google Drive MCP → uploads file
  - "What's on my calendar today?" → Composio Calendar MCP → returns events
- [ ] Composio Tool Router auto-discovers which toolkit matches the request
- [ ] Token usage from Composio calls logged to Neon (same api_calls table)


---

## PHASE 7: Corporate Platform
**Timeline: Week 10-16**
**Goal: The money maker — ₹300-₹1000/user/month.**

### 7A. Device Fleet Dashboard
- [ ] Admin sees all enrolled machines: CPU, RAM, disk, online/offline, last seen
- [ ] Status indicators: 🟢 healthy / 🟡 warning / 🔴 critical
- [ ] Click machine → see details, run remote diagnostics

### 7B. Ticketing + Escalation
- [ ] Employee → AI tries to solve → fail → auto-creates ticket
- [ ] Ticket includes: summary, steps tried, logs, screenshot, AI-suggested fix
- [ ] Admin notified via push/email

### 7C. Remote Support
- [ ] Human-to-human screen sharing (like TeamViewer)
- [ ] Optional remote control (with permission)
- [ ] "Request Help" button in employee app

### 7D. Policy Engine
- [ ] Block USB, restrict installs, enforce VPN from admin dashboard
- [ ] Push policy to all enrolled machines
- [ ] Role-based permissions: employee (read-only) / senior (restart) / admin (full)

### 7E. Silent Remote Actions
- [ ] Push overnight: restart, run script, install/uninstall
- [ ] Scheduled health scans (2am diagnostics)
- [ ] Anomaly alerts (disk spike, crashes, unusual processes)

---

## PHASE 8: Scale + Polish
**Timeline: Ongoing**

- [ ] Signed MCP tool responses (HMAC verification)
- [ ] Custom capability builder for org-specific tools (SAP, internal CRM)
- [ ] Session replay (1-FPS slideshow review)
- [ ] User segmentation (beginner/advanced, department-aware AI)
- [ ] Mobile admin app (push notifications for critical events)
- [ ] Ticket deflection metrics ("AI resolved 73% of issues, saved ₹18,400")
- [ ] A/B testing AI prompts per user segment


---

## Final Tech Stack (NO PYTHON)

| Layer | Technology | Language |
|-------|-----------|----------|
| Desktop App | **Tauri** (React + shadcn/ui + Radix UI) | Rust + TypeScript |
| Screen Capture | xcap crate (native) | Rust |
| Audio I/O | cpal crate (native) | Rust |
| Gemini WebSocket | tokio-tungstenite | Rust |
| Web Dashboard | Next.js + shadcn/ui (Vercel) | TypeScript |
| Auth | Clerk (web + desktop) | TypeScript |
| Database | Neon PostgreSQL | TypeScript (Drizzle ORM) |
| Memory | mem0 (backed by Neon) | TypeScript |
| Local MCP | DesktopCommanderMCP | TypeScript/Node.js |
| Cloud MCPs | **Composio** (Gmail, Drive, Calendar, Slack, 300+ apps) | TypeScript |
| AI Chat | OpenRouter (via CF Gateway) | TypeScript |
| AI Gateway | Cloudflare AI Gateway | TypeScript |
| Hosting | Vercel (frontend) | TypeScript |
| Token Optimization | Custom lean injection (NOT mcp2cli) | TypeScript |

---

## Pricing Tiers

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | Chat AI, limited live (low FPS), no remote support |
| Pro | $X/month | Full live AI, voice + screen, file/system actions, history |
| Corporate | ₹300-₹1000/user/month | Fleet dashboard, remote actions, policy, tickets, audit |

---

## Current Codebase Location
`C:\Users\hdavy2002\Documents\Website\windows -use\Windows-Use\`

## Environment Variables Needed
```
OPENROUTER_API_KEY=xxx
GEMINI_API_KEY=xxx
CLERK_PUBLISHABLE_KEY=xxx
CLERK_SECRET_KEY=xxx
NEON_DATABASE_URL=xxx
CLOUDFLARE_AI_GATEWAY_URL=xxx
```

---

*Document created: March 26, 2026*
*Status: Phase 1 ready to begin*
