"""
humphi/screen_capture.py — Frame capture + diff detection + adaptive FPS

Phase 2: Adaptive FPS ladder based on diff score.
Phase 3: Colour-aware capture, cursor awareness, 0 FPS truly idle.
"""

import base64
import io
import ctypes
import time
from PIL import Image, ImageGrab, ImageDraw

# Ultra-low res for fast streaming (~2-5 KB per frame)
CAPTURE_W, CAPTURE_H = 640, 360
DIFF_W, DIFF_H = 64, 36
JPEG_QUALITY = 15       # grayscale: aggressive compression
JPEG_QUALITY_COLOR = 20 # colour: slightly higher for fidelity
DIFF_THRESHOLD = 0.03

# Phase 3: Colour detection thresholds
# Percentage of pixels that must be red/orange/yellow to trigger colour mode
COLOR_TRIGGER_THRESHOLD = 0.015  # 1.5% of pixels

# ── Phase 2: Adaptive FPS ladder ──────────────────────────────────────────────
FPS_TIERS = [
    (0.02, 0.0),    # idle → skip
    (0.10, 0.5),    # minor → 2 sec
    (0.30, 1.0),    # normal → 1 sec
    (1.01, 2.0),    # active → 0.5 sec
]


def get_adaptive_delay(diff_score: float) -> float:
    """Return sleep delay in seconds based on screen change magnitude.
    Lower diff = longer delay (fewer frames sent = less cost).
    Returns -1 if frame should be skipped entirely (idle)."""
    for threshold, fps in FPS_TIERS:
        if diff_score < threshold:
            if fps <= 0:
                return -1  # skip frame
            return 1.0 / fps
    return 0.5  # default: 2 FPS


# ── Phase 3: Cursor position ─────────────────────────────────────────────────

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_position() -> tuple:
    """Get current mouse cursor position (x, y) using Win32 API."""
    try:
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)
    except Exception:
        return (0, 0)


# ── Phase 3: Colour-aware capture ─────────────────────────────────────────────

def _has_alert_colors(img: Image.Image) -> bool:
    """Check if image contains significant red/orange/yellow regions.
    These indicate error dialogs, warnings, trading alerts, etc.
    Samples a 64x36 thumbnail for speed."""
    thumb = img.resize((64, 36), Image.NEAREST).convert("RGB")
    pixels = list(thumb.getdata())
    alert_count = 0
    for r, g, b in pixels:
        # Red-ish: high red, low green+blue (errors, warnings, alerts)
        if r > 180 and g < 120 and b < 120:
            alert_count += 1
        # Orange-ish: high red, medium green, low blue (warnings)
        elif r > 180 and 80 < g < 160 and b < 80:
            alert_count += 1
        # Bright yellow: high red+green, low blue (caution dialogs)
        elif r > 200 and g > 180 and b < 80:
            alert_count += 1
    return (alert_count / len(pixels)) > COLOR_TRIGGER_THRESHOLD


def capture_frame(force_color: bool = False) -> str:
    """Capture screen → 360p → JPEG → base64.
    Phase 3: Detects alert colours → sends colour frame when needed.
    Returns: base64-encoded JPEG string."""
    img = ImageGrab.grab()
    use_color = force_color or _has_alert_colors(img)
    img = img.resize((CAPTURE_W, CAPTURE_H), Image.LANCZOS)
    if not use_color:
        img = img.convert("L")  # grayscale: ~2-5 KB
    buf = io.BytesIO()
    quality = JPEG_QUALITY_COLOR if use_color else JPEG_QUALITY
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_frame_with_metadata(exclude_rect=None) -> dict:
    """Phase 3: Capture frame + cursor position + colour mode flag.
    Returns dict with 'frame', 'cursor', 'is_color', 'timestamp'."""
    img = ImageGrab.grab()
    use_color = _has_alert_colors(img)
    cursor = get_cursor_position()

    # Exclude overlay rect from capture
    if exclude_rect:
        d = ImageDraw.Draw(img)
        x, y, w, h = exclude_rect
        d.rectangle([x, y, x+w, y+h], fill="black")

    img = img.resize((CAPTURE_W, CAPTURE_H), Image.LANCZOS)
    if not use_color:
        img = img.convert("L")
    buf = io.BytesIO()
    quality = JPEG_QUALITY_COLOR if use_color else JPEG_QUALITY
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "frame": b64,
        "cursor": cursor,
        "is_color": use_color,
        "timestamp": time.time(),
    }


# ── Diff detection ────────────────────────────────────────────────────────────

def compute_diff(fp_new: bytes, fp_old: bytes) -> float:
    """Compute diff score between two fingerprints. Returns 0.0-1.0."""
    if len(fp_new) != len(fp_old) or len(fp_new) == 0:
        return 1.0  # can't compare, treat as changed
    different = sum(1 for x, y in zip(fp_new, fp_old) if abs(x - y) > 30)
    return different / len(fp_new)


def _fingerprint(exclude_rect=None) -> bytes:
    """Tiny grayscale thumbnail for change detection."""
    img = ImageGrab.grab()
    if exclude_rect:
        d = ImageDraw.Draw(img)
        x, y, w, h = exclude_rect
        d.rectangle([x, y, x+w, y+h], fill="black")
    return img.resize((DIFF_W, DIFF_H), Image.NEAREST).convert("L").tobytes()


# ── Phase 3: 0 FPS truly idle ────────────────────────────────────────────────

class IdleDetector:
    """Track mouse + screen changes to detect true idle state.
    No mouse movement + no screen changes for N seconds = truly idle."""

    def __init__(self, idle_threshold_sec: float = 5.0):
        self._idle_threshold = idle_threshold_sec
        self._last_cursor = (0, 0)
        self._last_activity_time = time.time()
        self._consecutive_idle_frames = 0

    def update(self, diff_score: float) -> bool:
        """Update with latest diff score. Returns True if truly idle."""
        cursor = get_cursor_position()
        mouse_moved = cursor != self._last_cursor
        screen_changed = diff_score > 0.01

        if mouse_moved or screen_changed:
            self._last_activity_time = time.time()
            self._last_cursor = cursor
            self._consecutive_idle_frames = 0
            return False

        self._last_cursor = cursor
        self._consecutive_idle_frames += 1
        elapsed = time.time() - self._last_activity_time
        return elapsed >= self._idle_threshold

    @property
    def idle_seconds(self) -> float:
        return time.time() - self._last_activity_time

    @property
    def is_deeply_idle(self) -> bool:
        """True if idle for >30 seconds (no frames needed at all)."""
        return self.idle_seconds > 30.0
