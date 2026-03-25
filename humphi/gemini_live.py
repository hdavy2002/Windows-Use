"""
humphi/gemini_live.py — Gemini Live API Session Manager

Handles WebSocket connection to Gemini, cost controls,
session resets, and audio/video streaming.
"""

import asyncio
import json
import time
import base64
import websockets
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".humphi" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview"
GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
SESSION_MAX_SEC = 15 * 60       # Reset every 15 min
MAX_COST_PER_SESSION = 2.00     # USD hard cap
MIN_TURN_GAP_SEC = 15           # Max 4 turns/min
VOICE_NAME = "Aoede"            # Clear, professional

# Cost rates per 1M tokens
COST_VIDEO_IN = 0.30
COST_AUDIO_IN = 1.00
COST_AUDIO_OUT = 2.50
TOKENS_PER_FRAME_LOW = 66      # mediaResolution: 'low'
TOKENS_PER_SEC_AUDIO = 25

SYSTEM_INSTRUCTION = """You are an expert remote technical advisor. You can see the user's screen in real time and hear their voice. You have deep expertise across IT support, software troubleshooting, trading platforms, financial analysis, productivity software, network issues, and home technology.

YOUR ROLE:
- Act like a remote human expert who can see the user's screen but cannot touch their mouse
- Watch the screen continuously and understand context
- Give clear, step-by-step spoken instructions: "Click the Start button in the bottom left", "Look for the blue Settings icon"
- Reference specific things you see: "I can see the error message says...", "That red icon means..."

COMMUNICATION STYLE:
- Speak naturally and conversationally, like a calm expert on a phone call
- Keep responses concise — say what needs to be done, not why, unless asked
- Use landmarks: "the button next to the X", "the dropdown at the top"
- When waiting for user action: "Go ahead and click that, I'm watching"

SILENCE RULES (critical for cost):
- Do NOT narrate everything you see
- Do NOT describe the screen unless asked
- Do NOT speak unless user asks OR you spot a critical issue
- Stay silent while user carries out your instructions
- Only speak when: user asks, user seems stuck (60+ sec no progress), or you see an error

WHEN USER SAYS "PAUSE" OR "STOP":
- Stop all commentary, respond only when user says "resume" or asks a question

NEVER:
- Make up information you cannot see
- Guess if screen is unclear — ask user to describe
- Access or mention personal data beyond what's needed to help"""


def _dlog(msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line)
    try:
        f = LOG_DIR / f"live_{datetime.now().strftime('%Y-%m-%d')}.log"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except: pass


class GeminiLiveSession:
    """Manages a single live session with Gemini."""

    def __init__(self, api_key: str,
                 on_audio_out=None,
                 on_text_out=None,
                 on_turn_complete=None,
                 on_session_end=None):
        self.api_key = api_key
        self.on_audio_out = on_audio_out      # callback(pcm_bytes)
        self.on_text_out = on_text_out        # callback(text_str)
        self.on_turn_complete = on_turn_complete
        self.on_session_end = on_session_end

        self._ws = None
        self._running = False
        self._speaking = False  # True when Gemini is outputting audio
        self._start_time = 0
        self._turn_count = 0
        self._last_turn_time = 0
        self._total_tokens = 0
        self._total_cost = 0.0
        self._context_summary = ""
        self._recv_task = None

    @property
    def is_running(self):
        return self._running

    @property
    def is_speaking(self):
        return self._speaking

    async def connect(self):
        """Open WebSocket to Gemini Live API."""
        url = f"{GEMINI_WS_URL}?key={self.api_key}"
        _dlog(f"GEMINI: connecting to {GEMINI_MODEL}...")

        self._ws = await websockets.connect(url, max_size=None,
            close_timeout=5, ping_interval=30, ping_timeout=10)

        # Send setup message
        setup = {
            "setup": {
                "model": f"models/{GEMINI_MODEL}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "mediaResolution": "MEDIA_RESOLUTION_LOW",
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": VOICE_NAME
                            }
                        }
                    }
                },
                "systemInstruction": {
                    "parts": [{"text": SYSTEM_INSTRUCTION}]
                }
            }
        }

        await self._ws.send(json.dumps(setup))
        resp = await self._ws.recv()
        setup_resp = json.loads(resp)
        _dlog(f"GEMINI: connected, setup response received")

        self._running = True
        self._start_time = time.time()
        self._turn_count = 0
        self._total_cost = 0.0

        # Start receiving messages in background
        self._recv_task = asyncio.create_task(self._recv_loop())
        _dlog("GEMINI: session active, recv loop started")

    async def _recv_loop(self):
        """Receive messages from Gemini."""
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                msg = json.loads(raw)
                await self._handle_message(msg)
        except websockets.ConnectionClosed:
            _dlog("GEMINI: connection closed")
        except Exception as e:
            _dlog(f"GEMINI: recv error: {e}")
        finally:
            self._running = False

    async def _handle_message(self, msg):
        """Process incoming Gemini messages."""
        server_content = msg.get("serverContent")
        if not server_content:
            return

        # Check for turn complete
        turn_complete = server_content.get("turnComplete", False)
        if turn_complete:
            self._speaking = False
            self._turn_count += 1
            self._last_turn_time = time.time()
            _dlog(f"GEMINI: turn {self._turn_count} complete")
            if self.on_turn_complete:
                self.on_turn_complete()
            # Check cost controls
            await self._check_limits()
            return

        # Process model output parts
        model_turn = server_content.get("modelTurn", {})
        parts = model_turn.get("parts", [])

        for part in parts:
            # Audio output
            if "inlineData" in part:
                data = part["inlineData"]
                if data.get("mimeType", "").startswith("audio/"):
                    self._speaking = True
                    audio_bytes = base64.b64decode(data["data"])
                    if self.on_audio_out:
                        self.on_audio_out(audio_bytes)
            # Text output (transcript)
            elif "text" in part:
                text = part["text"]
                _dlog(f"GEMINI TEXT: {text[:100]}")
                if self.on_text_out:
                    self.on_text_out(text)

    # ── Send methods ──────────────────────────────────────────────────────

    async def send_video_frame(self, jpeg_b64: str):
        """Send a JPEG frame to Gemini."""
        if not self._running or self._speaking:
            return  # Don't send frames while AI is talking
        msg = {
            "realtimeInput": {
                "mediaChunks": [{
                    "mimeType": "image/jpeg",
                    "data": jpeg_b64
                }]
            }
        }
        await self._ws.send(json.dumps(msg))
        # Track cost
        cost = (TOKENS_PER_FRAME_LOW * COST_VIDEO_IN) / 1_000_000
        self._total_cost += cost

    async def send_audio(self, pcm_b64: str):
        """Send PCM audio chunk to Gemini."""
        if not self._running:
            return
        msg = {
            "realtimeInput": {
                "mediaChunks": [{
                    "mimeType": "audio/pcm;rate=16000",
                    "data": pcm_b64
                }]
            }
        }
        await self._ws.send(json.dumps(msg))

    async def send_text(self, text: str):
        """Send a text message to Gemini."""
        if not self._running:
            return
        msg = {
            "clientContent": {
                "turns": [{"role": "user", "parts": [{"text": text}]}],
                "turnComplete": True
            }
        }
        await self._ws.send(json.dumps(msg))
        _dlog(f"SENT TEXT: {text[:100]}")

    # ── Cost Controls ─────────────────────────────────────────────────────

    async def _check_limits(self):
        """Check session time and cost limits."""
        elapsed = time.time() - self._start_time

        # Session time limit — reset every 15 min
        if elapsed > SESSION_MAX_SEC:
            _dlog(f"COST: session at {elapsed:.0f}s, resetting...")
            await self._reset_session()
            return

        # Cost cap
        if self._total_cost > MAX_COST_PER_SESSION:
            _dlog(f"COST: ${self._total_cost:.2f} exceeds cap, resetting...")
            await self._reset_session()

    async def _reset_session(self):
        """Close session and reopen with context summary."""
        _dlog(f"RESET: closing session (turns={self._turn_count}, cost=${self._total_cost:.3f})")
        # Ask for summary before closing
        try:
            await self.send_text("Summarize what we've been working on in one sentence.")
            await asyncio.sleep(3)
        except: pass
        await self.disconnect()
        await asyncio.sleep(1)
        await self.connect()
        if self._context_summary:
            await self.send_text(f"CONTEXT: {self._context_summary}. Continue helping.")
        _dlog("RESET: new session started with context handoff")

    async def disconnect(self):
        """Close the session."""
        self._running = False
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws:
            try: await self._ws.close()
            except: pass
        elapsed = time.time() - self._start_time
        _dlog(f"GEMINI: disconnected (duration={elapsed:.0f}s, turns={self._turn_count}, cost=${self._total_cost:.3f})")
        if self.on_session_end:
            self.on_session_end()
