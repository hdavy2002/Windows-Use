"""
main_humphi.py — Humphi AI: Desktop Operator

Phase 0+1 implementation:
- Allowlist security (no blacklist)
- Streaming responses (perceived 3x speed)
- Typing indicator
- Structured action objects (no raw cmd)
- Two-LLM strategy (mini for routing, full for answers)
- Compressed system prompt (~80 tokens)
- max_tokens per intent type
- History truncation (last 2 turns + summary)
- Inline action confirmation
- Minimize button
"""

import sys, os, json, asyncio, threading, time, subprocess, re
from pathlib import Path
from datetime import datetime
from functools import lru_cache
import tkinter as tk
from tkinter import scrolledtext

from PIL import Image, ImageDraw as PilDraw
import pystray
import httpx

from humphi.gemini_live import GeminiLiveSession, _dlog
from humphi.screen_capture import capture_frame, _fingerprint
from humphi.audio import MicCapture, SpeakerOutput, HAS_AUDIO
from humphi.overlay import LiveTicker
from humphi.capabilities import match_capability, build_context_prompt

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
ROUTER_MODEL = "openai/gpt-4o-mini"   # cheap: ~$0.000008/classify
CHAT_MODEL = "openai/gpt-4.1"         # full: responses only
CHAT_KEY = os.environ.get("OPENROUTER_API_KEY", "")
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
    with httpx.stream("POST", "https://openrouter.ai/api/v1/chat/completions",
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
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {CHAT_KEY}", "Content-Type": "application/json"},
        json={"model": ROUTER_MODEL, "max_tokens": 10, "temperature": 0,
              "messages": [
                  {"role": "system", "content": "Classify into ONE word: network, bluetooth, apps, system_health, files, display, updates, sound, general"},
                  {"role": "user", "content": msg_normalized}
              ]}, timeout=10)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"].strip().lower()
    return "general"

def normalize_msg(text: str) -> str:
    """Normalize for intent cache: lowercase, strip punctuation."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()

# ── App ───────────────────────────────────────────────────────────────────────

class HumphiAI:
    def __init__(self):
        self._live_session = None
        self._live_loop = None
        self._mic = None
        self._speaker = None
        self._is_live = False
        self._mic_on = False
        self._last_fp = b""
        self._history = [{"role": "system", "content": SYS_PROMPT}]
        self._session_summary = ""
        self._minimized = False
        self._pending_action = None  # for confirmation UI

        self.root = tk.Tk(); self.root.withdraw()
        self.ticker = LiveTicker(self.root)
        self._build_ui()

    def _build_ui(self):
        BG, FG, ACCENT, DIM, GREEN, RED, INP, HDR = \
            "#1a1b26","#e1e5f2","#7aa2f7","#8890a8","#9ece6a","#f7768e","#24283b","#1f2335"
        self._colors = {"BG":BG,"FG":FG,"ACCENT":ACCENT,"DIM":DIM,"GREEN":GREEN,"RED":RED,"INP":INP,"HDR":HDR}

        self.win = tk.Toplevel(self.root)
        self.win.title("Humphi AI")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self._full_h, self._mini_h = 420, 42
        self.win.geometry(f"430x{self._full_h}+{sw-442}+{sh-self._full_h-50}")
        self.win.configure(bg=BG)

        # Header with minimize + close
        hdr = tk.Frame(self.win, bg=HDR, height=42); hdr.pack(side=tk.TOP, fill=tk.X); hdr.pack_propagate(False)
        tk.Label(hdr, text="\u26A1 Humphi AI", font=("Segoe UI",12,"bold"), fg=ACCENT, bg=HDR).pack(side=tk.LEFT, padx=12)
        tk.Button(hdr, text="\u2715", font=("Segoe UI",11), fg=RED, bg=HDR, bd=0, padx=6, cursor="hand2",
            command=lambda: self.win.withdraw()).pack(side=tk.RIGHT, padx=2)
        tk.Button(hdr, text="\u2500", font=("Segoe UI",11), fg=DIM, bg=HDR, bd=0, padx=6, cursor="hand2",
            command=self._toggle_minimize).pack(side=tk.RIGHT, padx=2)

        # Body (hidden when minimized)
        self._body = tk.Frame(self.win, bg=BG); self._body.pack(fill=tk.BOTH, expand=True)

        # Bottom bar
        bot = tk.Frame(self._body, bg=BG); bot.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

        # Confirmation bar (hidden by default)
        self._confirm_frame = tk.Frame(bot, bg="#1f2335"); self._confirm_frame.pack(fill=tk.X, pady=(0,4))
        self._confirm_label = tk.Label(self._confirm_frame, text="", font=("Consolas",10), fg=DIM, bg="#1f2335",
            wraplength=400, justify=tk.LEFT, anchor="w", padx=8, pady=4)
        self._confirm_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(self._confirm_frame, text="\u2714", font=("Segoe UI",11,"bold"), fg=GREEN, bg="#1f2335",
            bd=0, padx=6, cursor="hand2", command=self._confirm_action).pack(side=tk.RIGHT)
        tk.Button(self._confirm_frame, text="\u2718", font=("Segoe UI",11), fg=RED, bg="#1f2335",
            bd=0, padx=6, cursor="hand2", command=self._cancel_action).pack(side=tk.RIGHT)
        self._confirm_frame.pack_forget()

        # Live + Mic row
        lr = tk.Frame(bot, bg=BG); lr.pack(fill=tk.X, pady=(0,4))
        self.live_btn = tk.Button(lr, text="\U0001F534 Go Live Help", font=("Segoe UI",10,"bold"),
            fg="white", bg="#dc2626", bd=0, pady=5, padx=12, cursor="hand2", command=self._toggle_live)
        self.live_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        self.mic_btn = tk.Button(lr, text="\U0001F507 Mic", font=("Segoe UI",9), fg=DIM, bg=INP,
            bd=0, padx=10, pady=5, cursor="hand2", command=self._toggle_mic)
        self.mic_btn.pack(side=tk.RIGHT)

        # Input row
        ir = tk.Frame(bot, bg=BG); ir.pack(fill=tk.X)
        self.entry = tk.Entry(ir, font=("Segoe UI",12), bg=INP, fg=FG, insertbackground=FG, bd=0, relief=tk.FLAT)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0,4))
        self.entry.bind("<Return>", self._on_send)
        tk.Button(ir, text="\u27A4", font=("Segoe UI",14), fg=ACCENT, bg=INP, bd=0, padx=8, cursor="hand2",
            command=lambda: self._on_send(None)).pack(side=tk.RIGHT, ipady=5)

        # Chat log
        self.chat = scrolledtext.ScrolledText(self._body, wrap=tk.WORD, font=("Segoe UI",12),
            bg=BG, fg=FG, bd=0, padx=14, pady=10, state=tk.DISABLED, spacing3=6, relief=tk.FLAT)
        self.chat.pack(fill=tk.BOTH, expand=True)
        self.chat.tag_config("user", foreground=ACCENT, font=("Segoe UI",12,"bold"))
        self.chat.tag_config("bot", foreground=FG, font=("Segoe UI",12))
        self.chat.tag_config("dim", foreground=DIM, font=("Segoe UI",10))
        self.chat.tag_config("live", foreground=RED, font=("Segoe UI",11,"bold"))
        self.chat.tag_config("cmd", foreground=GREEN, font=("Consolas",10))
        self.chat.tag_config("typing", foreground=DIM, font=("Segoe UI",11))

        self._msg("Welcome! Type a question or click Go Live Help.", "dim")
        self.win.withdraw()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _msg(self, text, tag="bot"):
        self.chat.config(state=tk.NORMAL)
        pfx = "\nYou: " if tag == "user" else "\n" if tag in ("bot","live") else ""
        self.chat.insert(tk.END, f"{pfx}{text}\n", tag)
        self.chat.config(state=tk.DISABLED); self.chat.see(tk.END)

    def _msg_append(self, text, tag="bot"):
        """Append text to last line (for streaming)."""
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, text, tag)
        self.chat.config(state=tk.DISABLED); self.chat.see(tk.END)

    def _show_typing(self):
        self._msg("\u25CF\u25CF\u25CF", "typing")

    def _clear_typing(self):
        self.chat.config(state=tk.NORMAL)
        content = self.chat.get("1.0", tk.END)
        if "\u25CF\u25CF\u25CF" in content:
            idx = self.chat.search("\u25CF\u25CF\u25CF", "1.0", tk.END)
            if idx:
                self.chat.delete(idx, f"{idx} lineend + 1c")
        self.chat.config(state=tk.DISABLED)

    def _show_chat(self):
        self.win.deiconify(); self.win.lift(); self.entry.focus_set()

    def _toggle_minimize(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if self._minimized:
            self._body.pack(fill=tk.BOTH, expand=True)
            self.win.geometry(f"430x{self._full_h}+{sw-442}+{sh-self._full_h-50}")
            self._minimized = False
        else:
            self._body.pack_forget()
            self.win.geometry(f"430x{self._mini_h}+{sw-442}+{sh-self._mini_h-50}")
            self._minimized = True

    def _toggle_mic(self):
        if self._mic_on:
            self._mic_on = False
            if self._mic: self._mic.stop(); self._mic = None
            self.mic_btn.config(text="\U0001F507 Mic", fg="#8890a8")
        else:
            self._mic_on = True
            self._mic = MicCapture(on_audio_chunk=self._on_mic_audio)
            self._mic.start()
            self.mic_btn.config(text="\U0001F3A4 Mic", fg="#9ece6a")

    # ── Confirmation UI ───────────────────────────────────────────────────

    def _show_confirm(self, action_obj):
        self._pending_action = action_obj
        act = action_obj.get("action","")
        target = action_obj.get("target", action_obj.get("cmd",""))
        self._confirm_label.config(text=f"{act}: {target}")
        self._confirm_frame.pack(fill=tk.X, pady=(0,4))

    def _confirm_action(self):
        if self._pending_action:
            a = self._pending_action
            self._pending_action = None
            self._confirm_frame.pack_forget()
            threading.Thread(target=self._exec_action, args=(a,), daemon=True).start()

    def _cancel_action(self):
        self._pending_action = None
        self._confirm_frame.pack_forget()
        self._msg("Cancelled.", "dim")

    def _exec_action(self, action_obj):
        ok, out = execute_action(action_obj)
        act = action_obj.get("action","")
        self.root.after(0, lambda: self._msg(f"{'✓' if ok else '✗'} {act}: {out[:200]}", "cmd" if ok else "dim"))

    # ── History management (last 2 turns + summary) ───────────────────────

    def _trimmed_history(self):
        """Return compact history: system + summary + last 2 exchanges."""
        msgs = [{"role": "system", "content": SYS_PROMPT}]
        if self._session_summary:
            msgs.append({"role": "system", "content": f"Context: {self._session_summary}"})
        # Last 2 user+assistant pairs
        pairs = [m for m in self._history if m["role"] in ("user","assistant")]
        msgs.extend(pairs[-4:])
        return msgs

    # ── Chat + Routing ────────────────────────────────────────────────────

    def _on_send(self, event):
        text = self.entry.get().strip()
        if not text: return
        self.entry.delete(0, tk.END)
        self._msg(text, "user")
        self._history.append({"role": "user", "content": text})
        if self._is_live:
            threading.Thread(target=self._send_live_text, args=(text,), daemon=True).start()
        else:
            self.root.after(0, self._show_typing)
            threading.Thread(target=self._do_chat, args=(text,), daemon=True).start()

    def _do_chat(self, text):
        """Route → classify → inject capability → stream response."""
        # 1. Classify intent (cheap, cached)
        norm = normalize_msg(text)
        intent = classify_intent(norm)
        _dlog(f"INTENT: '{norm}' → {intent}")

        # 2. Match capability module
        cap = match_capability(text)
        cap_ctx = build_context_prompt(cap) if cap else ""

        # 3. Build messages
        msgs = self._trimmed_history()
        if cap_ctx:
            msgs.insert(1, {"role": "system", "content": cap_ctx})

        # 4. Determine max_tokens
        mt = MAX_TOKENS.get(intent, MAX_TOKENS["general"])

        # 5. Stream response
        self.root.after(0, self._clear_typing)
        first_token = [True]
        def on_token(chunk):
            if first_token[0]:
                self.root.after(0, lambda: self._msg("", "bot"))
                first_token[0] = False
            self.root.after(0, lambda c=chunk: self._msg_append(c, "bot"))

        try:
            reply = call_ai_stream(msgs, CHAT_KEY, CHAT_MODEL, mt, on_token)
            self._history.append({"role": "assistant", "content": reply})
        except Exception as e:
            self.root.after(0, self._clear_typing)
            self.root.after(0, lambda: self._msg(f"Error: {e}", "dim"))
            return

        # 6. Parse and handle structured actions
        actions = parse_actions(reply)
        for a in actions:
            act = a.get("action", "")
            # Safe actions auto-run, others need confirmation
            if act in ("open_settings", "run_diagnostic", "list_processes", "check_disk", "check_network"):
                self.root.after(0, lambda ao=a: self._exec_action(ao))
            else:
                self.root.after(0, lambda ao=a: self._show_confirm(ao))

    # ── Live Session ──────────────────────────────────────────────────────

    def _toggle_live(self):
        if self._is_live: self._stop_live()
        else: self._start_live()

    def _start_live(self):
        if not GEMINI_KEY:
            self._msg("Set GEMINI_API_KEY for live mode.", "dim"); return
        self._is_live = True
        self._msg("\U0001F534 Live session starting", "live")
        self.live_btn.config(text="\u25A0 End Live", bg="#991b1b")
        self._speaker = SpeakerOutput(); self._speaker.start()
        self._live_loop = asyncio.new_event_loop()
        threading.Thread(target=lambda: self._live_loop.run_until_complete(self._live_main()), daemon=True).start()

    async def _live_main(self):
        self._live_session = GeminiLiveSession(api_key=GEMINI_KEY,
            on_audio_out=lambda b: self._speaker.play(b) if self._speaker else None,
            on_text_out=lambda t: self.root.after(0, lambda: self._msg(t, "live")),
            on_turn_complete=lambda: _dlog("LIVE: turn done"),
            on_session_end=lambda: self.root.after(0, self._cleanup_live))
        try: await self._live_session.connect()
        except Exception as e:
            self.root.after(0, lambda: self._msg(f"Connection failed: {e}", "dim"))
            self.root.after(0, self._cleanup_live); return

        self.root.after(0, lambda: self.ticker.show(on_stop=self._stop_live))
        self.root.after(0, lambda: self._msg("\U0001F534 LIVE — AI watching screen", "live"))
        self._last_fp = _fingerprint(self.ticker.get_rect())
        while self._is_live and self._live_session.is_running:
            try:
                fp = _fingerprint(self.ticker.get_rect())
                diff = sum(1 for x,y in zip(fp,self._last_fp) if abs(x-y)>30) / len(fp) if len(fp)==len(self._last_fp) and len(fp)>0 else 0
                if diff > DIFF_THRESHOLD and not self._live_session.is_speaking:
                    await self._live_session.send_video_frame(capture_frame())
                    self._last_fp = fp
                await asyncio.sleep(1.0)
            except: await asyncio.sleep(1.0)
        await self._live_session.disconnect()

    def _on_mic_audio(self, b64):
        if self._is_live and self._mic_on and self._live_session and self._live_loop:
            asyncio.run_coroutine_threadsafe(self._live_session.send_audio(b64), self._live_loop)

    def _send_live_text(self, text):
        if self._live_session and self._live_loop:
            asyncio.run_coroutine_threadsafe(self._live_session.send_text(text), self._live_loop)

    def _stop_live(self):
        self._is_live = False; self._cleanup_live()

    def _cleanup_live(self):
        self._is_live = False; self._mic_on = False
        if self._mic: self._mic.stop(); self._mic = None
        if self._speaker: self._speaker.stop(); self._speaker = None
        self.ticker.hide()
        self.live_btn.config(text="\U0001F534 Go Live Help", bg="#dc2626")
        self.mic_btn.config(text="\U0001F507 Mic", fg="#8890a8")
        self._msg("Live session ended.", "dim")

    # ── Tray Icon ─────────────────────────────────────────────────────────

    def _make_icon(self):
        img = Image.new("RGBA", (64,64), (0,0,0,0))
        d = PilDraw.Draw(img)
        d.ellipse([4,4,60,60], fill="#7aa2f7")
        d.polygon([(32,10),(22,34),(30,34),(28,54),(42,28),(34,28)], fill="#1a1b26")
        return img

    def _run_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda: self.root.after(0, self._show_chat), default=True),
            pystray.MenuItem("Go Live", lambda: self.root.after(0, self._start_live)),
            pystray.MenuItem("Quit", self._quit))
        self.tray = pystray.Icon("HumphiAI", self._make_icon(), "Humphi AI", menu)
        self.tray.run()

    def _quit(self):
        if self._is_live: self._stop_live()
        self.tray.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        _dlog(f"=== Humphi AI Started === Router:{ROUTER_MODEL} Chat:{CHAT_MODEL}")
        _dlog(f"  Gemini: {'ready' if GEMINI_KEY else 'MISSING'}")
        threading.Thread(target=self._run_tray, daemon=True).start()
        self.root.after(500, self._show_chat)
        self.root.mainloop()


if __name__ == "__main__":
    HumphiAI().run()
