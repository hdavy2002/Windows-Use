"""
humphi/screen_capture.py — Frame capture + diff detection

Captures desktop at 1 FPS, detects changes, sends only changed frames.
"""

import base64
import io
import asyncio
from PIL import Image, ImageGrab, ImageDraw

# Ultra-low res for fast streaming (~2-5 KB per frame)
CAPTURE_W, CAPTURE_H = 640, 360
DIFF_W, DIFF_H = 64, 36
JPEG_QUALITY = 15  # aggressive compression, still readable for UI text
DIFF_THRESHOLD = 0.03


def capture_frame() -> str:
    """Capture screen → 360p → grayscale → JPEG 15% → ~2-5 KB base64."""
    img = ImageGrab.grab()
    img = img.resize((CAPTURE_W, CAPTURE_H), Image.LANCZOS)
    img = img.convert("L")  # grayscale cuts size in half
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _fingerprint(exclude_rect=None) -> bytes:
    """Tiny grayscale thumbnail for change detection."""
    img = ImageGrab.grab()
    if exclude_rect:
        d = ImageDraw.Draw(img)
        x, y, w, h = exclude_rect
        d.rectangle([x, y, x+w, y+h], fill="black")
    return img.resize((DIFF_W, DIFF_H), Image.NEAREST).convert("L").tobytes()
