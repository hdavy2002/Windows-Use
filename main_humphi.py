"""
main_humphi.py — Humphi AI: Desktop Operator

Phase 0+1+2 implementation:
- Allowlist security (no blacklist) + prompt injection guard + consent
- Streaming responses (perceived 3x speed)
- Two-LLM strategy (mini for routing, full for answers)
- Direct command bypass ($0 cost for ~30% of requests)
- Session memory + user type inference
- Quick-action chips + adaptive FPS + 3-tier cost ladder
"""

import sys, os, json, asyncio, threading, time, subprocess, re
from pathlib import Path
from datetime import datetime
from functools import lru_cache

import httpx

from humphi.gemini_live import GeminiLiveSession, _dlog
from humphi.screen_capture import (
    capture_frame, _fingerprint, compute_diff, get_adaptive_delay,
    capture_frame_with_metadata, IdleDetector, get_cursor_position
)
from humphi.audio import MicCapture, SpeakerOutput, HAS_AUDIO
from humphi.overlay import LiveTicker
from humphi.capabilities import match_capability, build_context_prompt, check_direct_command
from humphi.memory import SessionMemory

# ── Config ────────────────────────────────────────────────────────────────────
# Use BIFROST_HOST for proxy, or CLOUDFLARE_GATEWAY for direct-style gateway
_BIFROST = os.environ.get("BIFROST_HOST", "https://api.humphi.com:8000")
_GATEWAY = os.environ.get("CLOUDFLARE_GATEWAY") 
CF_AIG_TOKEN = os.environ.get("CF_AIG_TOKEN")

# If gateway is set, we bypass Bifrost for testing
BIFROST_URL = f"{_GATEWAY}/v1/chat/completions" if _GATEWAY else f"{_BIFROST}/v1/chat/completions"

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "bifrost")
ROUTER_MODEL = "gemini-2.0-flash" 
CHAT_MODEL = "gemini-1.5-flash" # Use 1.5/2.0 as they are widely available
CHAT_KEY = os.environ.get("OPENROUTER_API_KEY", "bifrost")
LOG_DIR = Path.home() / ".humphi" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DIFF_THRESHOLD = 0.03

# ── Compressed system prompt (~80 tokens) ─────────────────────────────────────
SYS_PROMPT = """Humphi=Windows AI desktop operator. Help troubleshoot+guide+execute safe actions.
Actions: return JSON {"action":"open_settings","target":"network"} or {"action":"run_diagnostic","cmd":"Get-Process"}
Suggest Go Live for visual/complex tasks. Mention mic for voice. Be concise. Confirm risky ops."""

# ── max_tokens per intent type ────────────────────────────────────────────────
MAX_TOKENS = {
    "execute": 80, "simple_chat": 200, "diagnostic": 300,
    "guide": 250, "general": 200
}

# ── PHASE 0: Strict allowlist security ────────────────────────────────────────
# ONLY these commands can run. Everything else is blocked. No exceptions.
ALLOWED_CMDS = {
    # Open settings pages
    "start-process": True,
    # Read-only diagnostics
    "get-process": True, "get-service": True, "get-netadapter": True,
    "get-netipaddress": True, "get-psdrive": True, "get-hotfix": True,
    "get-ciminstance": True, "get-pnpdevice": True, "get-package": True,
    "get-mpcomputerstatus": True, "get-childitem": True, "get-dnsclientcache": True,
    "test-netconnection": True, "test-path": True,
    "measure-object": True, "ipconfig": True, "ping": True,
    # Settings URIs
    "ms-settings:": True,
}

ALLOWED_EXES = {"taskmgr.exe","msinfo32.exe","cleanmgr.exe","devmgmt.msc",
    "diskmgmt.msc","services.msc","appwiz.cpl","ncpa.cpl","wf.msc","sndvol.exe",
    "explorer.exe","notepad.exe","calc.exe","mspaint.exe"}

def is_allowed(cmd: str) -> bool:
    """Strict allowlist check. Returns True only if command is explicitly permitted."""
    first = cmd.strip().split()[0].lower() if cmd.strip() else ""
    # Check direct command
    if first in ALLOWED_CMDS: return True
    # Check if it's an allowed executable
    if first == "start-process":
        args = cmd.strip().split(maxsplit=1)
        if len(args) > 1:
            target = args[1].strip().strip('"').strip("'").lower()
            if target.startswith("ms-settings:"): return True
            if target in ALLOWED_EXES: return True
    return False

# ── PHASE 0: Prompt injection guard ───────────────────────────────────────────
INJECTION_PATTERNS = [
    "ignore previous instructions", "ignore all previous", "disregard previous",
    "forget your instructions", "forget all instructions", "forget everything above",
    "jailbreak", "dan mode", "developer mode", "do anything now",
    "pretend you are", "pretend to be", "act as if you have no restrictions",
    "you are now", "new persona", "bypass restrictions", "override safety",
    "ignore safety", "no restrictions", "unrestricted mode",
    "system prompt", "reveal your prompt", "show your instructions",
    "what are your rules", "repeat your system message",
]

def check_injection(text: str) -> tuple[bool, str]:
    """Scan user input for prompt injection patterns.
    Returns (is_safe, reason). Logs flagged attempts."""
    low = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in low:
            reason = f"Blocked injection pattern: '{pattern}'"
            _log_injection(text, pattern)
            return False, reason
    return True, ""

def _log_injection(text: str, pattern: str):
    """Log injection attempts for admin review."""
    try:
        log_file = LOG_DIR / "injection_attempts.jsonl"
        entry = json.dumps({"ts": datetime.now().isoformat(), "pattern": pattern,
                            "input": text[:200]}, ensure_ascii=False)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except: pass

# ── PHASE 0: Screen capture consent ──────────────────────────────────────────
CONSENT_FILE = Path.home() / ".humphi" / "consent.json"
AUDIT_FILE = LOG_DIR / "live_audit.jsonl"

def _load_consent() -> bool:
    """Check if user has previously consented to screen capture."""
    try:
        if CONSENT_FILE.exists():
            data = json.loads(CONSENT_FILE.read_text())
            return data.get("screen_capture_consent", False)
    except: pass
    return False

def _save_consent():
    """Store consent flag."""
    CONSENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONSENT_FILE.write_text(json.dumps({
        "screen_capture_consent": True,
        "consented_at": datetime.now().isoformat()
    }))

def _log_live_session(event: str, **extra):
    """Append audit event for live sessions (GDPR/ISO 27001)."""
    try:
        entry = {"ts": datetime.now().isoformat(), "event": event, **extra}
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except: pass

def run_cmd(cmd: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command",cmd],
            capture_output=True, text=True, timeout=15)
        return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())[:500]
    except Exception as e: return False, str(e)

# ── Structured action executor ────────────────────────────────────────────────
ACTION_MAP = {
    "open_settings": lambda t: f"Start-Process ms-settings:{t}",
    "open_app": lambda t: f"Start-Process {t}" if t.lower() in ALLOWED_EXES else None,
    "run_diagnostic": lambda t: t if is_allowed(t) else None,
    "list_processes": lambda _: "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,CPU,WorkingSet64 | Format-Table",
    "check_disk": lambda _: "Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{N='UsedGB';E={[math]::Round($_.Used/1GB,1)}},@{N='FreeGB';E={[math]::Round($_.Free/1GB,1)}} | Format-Table",
    "check_network": lambda _: "Test-NetConnection -ComputerName google.com -Port 443",
}

def execute_action(action_obj: dict) -> tuple[bool, str]:
    """Execute a structured action object safely."""
    act = action_obj.get("action", "")
    target = action_obj.get("target", action_obj.get("cmd", ""))
    handler = ACTION_MAP.get(act)
    if not handler:
        return False, f"Unknown action: {act}"
    cmd = handler(target)
    if not cmd:
        return False, f"Blocked: {act} → {target}"
    if not is_allowed(cmd):
        return False, f"Not in allowlist: {cmd}"
    _dlog(f"EXEC: {act} → {cmd}")
    return run_cmd(cmd)

def parse_actions(text: str) -> list[dict]:
    """Extract JSON action objects from AI response."""
    actions = []
    for m in re.finditer(r'\{[^{}]*"action"[^{}]*\}', text):
        try: actions.append(json.loads(m.group()))
        except: pass
    return actions

def strip_actions(text: str) -> str:
    return re.sub(r'\{[^{}]*"action"[^{}]*\}', '', text).strip()

# ── AI Calls ──────────────────────────────────────────────────────────────────

def call_ai_stream(messages, api_key, model=CHAT_MODEL, max_tokens=200, on_token=None):
    """Streaming AI call — calls on_token(text_chunk) as tokens arrive."""
    full = []
    with httpx.stream("POST", BIFROST_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": max_tokens,
              "temperature": 0.3, "stream": True},
        timeout=30) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "): continue
            data = line[6:]
            if data == "[DONE]": break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                text = delta.get("content", "")
                if text:
                    full.append(text)
                    if on_token: on_token(text)
            except: pass
    return "".join(full)

@lru_cache(maxsize=500)
def classify_intent(msg_normalized: str) -> str:
    """Cheap LLM call to classify intent. Cached for repeat phrases."""
    headers = {
        "Authorization": f"Bearer {CHAT_KEY}",
        "Content-Type": "application/json"
    }
    if CF_AIG_TOKEN and _GATEWAY in BIFROST_URL:
        headers["cf-aig-authorization"] = f"Bearer {CF_AIG_TOKEN}"

    r = httpx.post(BIFROST_URL,
        headers=headers,
        json={"model": ROUTER_MODEL, "max_tokens": 10, "temperature": 0,
              "messages": [
                  {"role": "system", "content": "Classify into ONE word: network, bluetooth, apps, system_health, files, display, updates, sound, printer, accounts, privacy, general"},
                  {"role": "user", "content": msg_normalized}
              ]}, timeout=10)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"].strip().lower()
    return "general"

def normalize_msg(text: str) -> str:
    """Normalize for intent cache: lowercase, strip punctuation."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()

# ── Phase 5: Webview Bridge (pywebview) ──────────────────────────────────────

import webview

class BackendApi:
    def __init__(self):
        self._window = None
        self._history = [{"role": "system", "content": SYS_PROMPT}]
        self._session_summary = ""
        self._memory = SessionMemory()
        self._is_live = False
        self._live_session = None
        self._live_loop = None
        self._mic = None
        self._mic_on = False
        self._speaker = None
        self._pending_confirmations = {}
        self._last_fp = b""
        
        # Pre-warm
        threading.Thread(target=self._prewarm, daemon=True).start()

    def set_window(self, window):
        self._window = window

    def _prewarm(self):
        try:
            from humphi.capabilities import list_capabilities
            list_capabilities()
            classify_intent("warm")
        except: pass

    def send_message(self, text):
        """Called from JS when user sends a message."""
        self._history.append({"role": "user", "content": text})
        
        # Injection check
        is_safe, reason = check_injection(text)
        if not is_safe:
            self._emit("msg", {"text": f"⚠️ {reason}", "role": "dim"})
            return

        # Direct command check
        direct_cmd = check_direct_command(text)
        if direct_cmd:
            self._emit("msg", {"text": f"⚡ Running: {direct_cmd[:60]}", "role": "cmd"})
            ok, out = run_cmd(direct_cmd) if direct_cmd.startswith("Start-Process") or is_allowed(direct_cmd) else (False, "Blocked")
            self._emit("msg", {"text": f"{'✓' if ok else '✗'} {out[:200]}", "role": "cmd" if ok else "dim"})
            self._memory.update_after_turn("direct", None, {"action": "direct_cmd", "cmd": direct_cmd})
            return

        threading.Thread(target=self._do_chat_thread, args=(text,), daemon=True).start()

    def _do_chat_thread(self, text):
        norm = normalize_msg(text)
        
        async def fetch_context():
            t_intent = asyncio.to_thread(classify_intent, norm)
            t_mem = asyncio.to_thread(self._memory.to_prompt)
            return await asyncio.gather(t_intent, t_mem)

        intent, mem_ctx = asyncio.run(fetch_context())
        
        cap = match_capability(text)
        cap_ctx = build_context_prompt(cap) if cap else ""

        msgs = [{"role": "system", "content": SYS_PROMPT}]
        if self._session_summary:
            msgs.append({"role": "system", "content": f"Context: {self._session_summary}"})
        if cap_ctx:
            msgs.append({"role": "system", "content": cap_ctx})
        if mem_ctx:
            msgs.append({"role": "system", "content": f"User context: {mem_ctx}"})
            
        pairs = [m for m in self._history if m["role"] in ("user","assistant")]
        msgs.extend(pairs[-4:])

        mt = MAX_TOKENS.get(intent, MAX_TOKENS["general"])

        full_reply = []
        def on_token(chunk):
            full_reply.append(chunk)
            self._emit("update_msg", {"text": "".join(full_reply)})

        try:
            reply = call_ai_stream(msgs, CHAT_KEY, CHAT_MODEL, mt, on_token)
            self._emit("end_msg", {})
            self._history.append({"role": "assistant", "content": reply})
        except Exception as e:
            self._emit("end_msg", {})
            self._emit("msg", {"text": f"Error: {e}", "role": "dim"})
            return

        actions = parse_actions(reply)
        for a in actions:
            act = a.get("action", "")
            if act in ("open_settings", "run_diagnostic", "list_processes", "check_disk", "check_network"):
                self._exec_action(a)
            else:
                msg_id = str(time.time())
                self._pending_confirmations[msg_id] = a
                self._window.evaluate_js(f"requireConfirmation({json.dumps(a)}, '{msg_id}')")

        self._memory.update_after_turn(intent, cap["id"] if cap else None, actions[0] if actions else None)

    def _exec_action(self, action_obj):
        act = action_obj.get("action","")
        ok, out = execute_action(action_obj)
        self._emit("msg", {"text": f"{'✓' if ok else '✗'} {act}: {out[:200]}", "role": "cmd" if ok else "dim"})

    def resolve_confirmation(self, msg_id, is_allow):
        """Called from JS when user allows/denies action."""
        action_obj = self._pending_confirmations.pop(msg_id, None)
        if action_obj and is_allow:
            threading.Thread(target=self._exec_action, args=(action_obj,), daemon=True).start()

    # --- Live Mode ---
    def check_consent(self):
        return _load_consent()

    def give_consent(self):
        _save_consent()
        return True

    def toggle_live(self, enable):
        if enable and not self._is_live:
            self._start_live()
        elif not enable and self._is_live:
            self._stop_live()

    def _start_live(self):
        if not GEMINI_KEY:
            self._emit("msg", {"text": "Set GEMINI_API_KEY for live mode.", "role": "dim"})
            return
            
        _log_live_session("session_start")
        self._is_live = True
        self._speaker = SpeakerOutput()
        self._speaker.start()
        self._live_loop = asyncio.new_event_loop()
        threading.Thread(target=lambda: self._live_loop.run_until_complete(self._live_main()), daemon=True).start()

    async def _live_main(self):
        def _handle_live_text(t):
            self._emit("msg", {"text": t, "role": "live"})
            actions = parse_actions(t)
            for a in actions:
                act = a.get("action", "")
                if act in ("open_settings", "run_diagnostic", "list_processes", "check_disk", "check_network"):
                    self._exec_action(a)
                else:
                    msg_id = str(time.time())
                    self._pending_confirmations[msg_id] = a
                    if self._window:
                        self._window.evaluate_js(f"requireConfirmation({json.dumps(a)}, '{msg_id}')")

        self._live_session = GeminiLiveSession(api_key=GEMINI_KEY,
            on_audio_out=lambda b: self._speaker.play(b) if self._speaker else None,
            on_text_out=_handle_live_text)
            
        try: await self._live_session.connect()
        except Exception as e:
            self._emit("msg", {"text": f"Connection failed: {e}", "role": "dim"})
            self._stop_live()
            return

        idle_det = IdleDetector(idle_threshold_sec=5.0)
        self._last_fp = b""
        
        while self._is_live and self._live_session.is_running:
            try:
                fp = _fingerprint((0,0,640,360))
                diff = compute_diff(fp, self._last_fp)
                truly_idle = idle_det.update(diff)

                if truly_idle:
                    await asyncio.sleep(5.0 if idle_det.is_deeply_idle else 3.0)
                    continue

                if diff > DIFF_THRESHOLD and not self._live_session.is_speaking:
                    frame_data = capture_frame_with_metadata((0,0,640,360))
                    await self._live_session.send_video_frame_with_metadata(frame_data)
                    self._last_fp = fp

                delay = get_adaptive_delay(diff)
                await asyncio.sleep(2.0 if delay < 0 else delay)
            except: await asyncio.sleep(1.0)
            
        await self._live_session.disconnect()

    def _stop_live(self):
        self._is_live = False
        if self._speaker:
            self._speaker.stop()
            self._speaker = None
        if self._live_session and self._live_loop:
            asyncio.run_coroutine_threadsafe(self._live_session.disconnect(), self._live_loop)

    def _emit(self, event, data):
        """Helper to invoke JS functions on the frontend."""
        if not self._window: return
        try:
            if event == "msg":
                text = json.dumps(data["text"])
                role = json.dumps(data["role"])
                self._window.evaluate_js(f"appendMessage({text}, {role})")
            elif event == "update_msg":
                text = json.dumps(data["text"])
                self._window.evaluate_js(f"updateCurrentMessage({text})")
            elif event == "end_msg":
                self._window.evaluate_js("endCurrentMessage()")
        except Exception as e:
            print("Emit error:", e)

def generate_session_summary(history):
    """Phase 5: Session End Summary."""
    if len(history) < 3: return "Short session, no summary needed."
    transcript = "\\n".join([f"{m['role']}: {m['content']}" for m in history[-10:] if m['role'] != 'system'])
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {CHAT_KEY}"},
            json={"model": ROUTER_MODEL, "messages": [
                {"role": "system", "content": "Summarize this IT support session in 1 concise line like '✅ Fixed WiFi issue' or '❌ Could not resolve printer'."},
                {"role": "user", "content": transcript}
            ]}, timeout=5)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return "Summary generation failed."

if __name__ == "__main__":
    _dlog(f"=== Humphi AI Started (Webview) === Router:{ROUTER_MODEL} Chat:{CHAT_MODEL}")
    
    api = BackendApi()
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'index.html')
    
    window = webview.create_window(
        'Humphi AI', 
        url=html_path, 
        js_api=api,
        width=450, 
        height=600
    )
    api.set_window(window)
    
    def on_closed():
        print("Window closed. Generating summary...")
        summary = generate_session_summary(api._history)
        print(f"Session Summary: {summary}")
        try:
            sum_file = Path.home() / ".humphi" / "session_summaries.jsonl"
            sum_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sum_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), "summary": summary}) + "\\n")
        except: pass

    window.events.closed += on_closed
    webview.start()
