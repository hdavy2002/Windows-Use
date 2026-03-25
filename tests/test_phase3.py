"""
tests/test_phase3.py — Phase 3: Live Mode Upgrade tests

Tests: colour detection, cursor position, IdleDetector, adaptive delay,
       guidance command parsing, confidence signals, capture_frame_with_metadata.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── IdleDetector tests ────────────────────────────────────────────────────────

from humphi.screen_capture import (
    IdleDetector, get_adaptive_delay, _has_alert_colors,
    CAPTURE_W, CAPTURE_H, DIFF_W, DIFF_H
)


def test_idle_detector_init():
    det = IdleDetector(idle_threshold_sec=3.0)
    assert det._idle_threshold == 3.0
    assert det._consecutive_idle_frames == 0


def test_idle_detector_not_idle_on_movement():
    det = IdleDetector(idle_threshold_sec=0.1)
    # Simulating screen change
    result = det.update(0.5)  # large diff = screen changed
    assert result == False  # not idle


def test_idle_detector_idle_after_threshold():
    det = IdleDetector(idle_threshold_sec=0.01)
    # Set last cursor to actual current cursor to avoid false movement
    from humphi.screen_capture import get_cursor_position
    det._last_cursor = get_cursor_position()
    # Force last activity to be old
    det._last_activity_time = time.time() - 1.0
    # No screen change, same cursor
    result = det.update(0.001)
    # cursor hasn't changed and diff < 0.01 and elapsed > threshold
    assert result == True


def test_idle_detector_deeply_idle():
    det = IdleDetector(idle_threshold_sec=1.0)
    det._last_activity_time = time.time() - 35.0
    assert det.is_deeply_idle == True


def test_idle_detector_not_deeply_idle():
    det = IdleDetector(idle_threshold_sec=1.0)
    det._last_activity_time = time.time() - 5.0
    assert det.is_deeply_idle == False


def test_idle_seconds():
    det = IdleDetector()
    det._last_activity_time = time.time() - 10.0
    assert det.idle_seconds >= 9.5


# ── Adaptive delay tests ─────────────────────────────────────────────────────

def test_adaptive_delay_idle():
    assert get_adaptive_delay(0.01) == -1  # skip frame


def test_adaptive_delay_minor():
    delay = get_adaptive_delay(0.05)
    assert delay == 2.0  # 0.5 FPS = 2 sec


def test_adaptive_delay_normal():
    delay = get_adaptive_delay(0.15)
    assert delay == 1.0  # 1 FPS = 1 sec


def test_adaptive_delay_active():
    delay = get_adaptive_delay(0.35)
    assert delay == 0.5  # 2 FPS = 0.5 sec


# ── Colour detection tests ───────────────────────────────────────────────────

from PIL import Image

def test_no_alert_colors_on_gray():
    """A fully gray image should not trigger colour mode."""
    img = Image.new("RGB", (640, 360), (128, 128, 128))
    assert _has_alert_colors(img) == False


def test_alert_colors_on_red_image():
    """An image with significant red pixels should trigger colour mode."""
    img = Image.new("RGB", (640, 360), (220, 40, 40))
    assert _has_alert_colors(img) == True


def test_alert_colors_on_orange():
    """Orange warning colours should trigger."""
    img = Image.new("RGB", (640, 360), (230, 120, 30))
    assert _has_alert_colors(img) == True


def test_alert_colors_on_yellow():
    """Bright yellow caution should trigger."""
    img = Image.new("RGB", (640, 360), (240, 220, 30))
    assert _has_alert_colors(img) == True


def test_no_alert_colors_on_blue():
    """Blue screen should not trigger colour mode."""
    img = Image.new("RGB", (640, 360), (30, 80, 220))
    assert _has_alert_colors(img) == False


def test_no_alert_colors_on_dark():
    """Dark screen (typical idle desktop) should not trigger."""
    img = Image.new("RGB", (640, 360), (26, 27, 38))
    assert _has_alert_colors(img) == False


# ── Guidance command parsing tests ────────────────────────────────────────────

from humphi.gemini_live import GeminiLiveSession


def test_parse_highlight_command():
    """HIGHLIGHT(x, y, w, h, text) should be parsed and stripped."""
    captured = []
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = lambda t, a: captured.append((t, a))
    result = session._parse_guidance_cmds(
        "Click here HIGHLIGHT(100, 200, 150, 40, Start button) to begin")
    assert "HIGHLIGHT" not in result
    assert len(captured) == 1
    assert captured[0][0] == "highlight"
    assert captured[0][1]["x"] == 100
    assert captured[0][1]["y"] == 200
    assert captured[0][1]["text"] == "Start button"


def test_parse_signal_command():
    """SIGNAL(act) should be parsed and stripped."""
    captured = []
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = lambda t, a: captured.append((t, a))
    result = session._parse_guidance_cmds("Price alert! SIGNAL(act) Check now.")
    assert "SIGNAL" not in result
    assert len(captured) == 1
    assert captured[0][0] == "signal"
    assert captured[0][1]["type"] == "act"


def test_parse_signal_watch():
    captured = []
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = lambda t, a: captured.append((t, a))
    session._parse_guidance_cmds("SIGNAL(watch)")
    assert captured[0][1]["type"] == "watch"


def test_parse_signal_prepare():
    captured = []
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = lambda t, a: captured.append((t, a))
    session._parse_guidance_cmds("SIGNAL(prepare)")
    assert captured[0][1]["type"] == "prepare"


def test_parse_no_commands():
    """Regular text without commands should pass through unchanged."""
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = None
    result = session._parse_guidance_cmds("Just a normal response with no commands")
    assert result == "Just a normal response with no commands"


def test_parse_multiple_highlights():
    """Multiple HIGHLIGHT commands in one response."""
    captured = []
    session = GeminiLiveSession.__new__(GeminiLiveSession)
    session.on_guidance_cmd = lambda t, a: captured.append((t, a))
    session._parse_guidance_cmds(
        "HIGHLIGHT(10, 20, 100, 50, Button A) and HIGHLIGHT(200, 300, 80, 30, Button B)")
    assert len(captured) == 2
    assert captured[0][1]["text"] == "Button A"
    assert captured[1][1]["text"] == "Button B"


# ── Constants sanity checks ──────────────────────────────────────────────────

def test_capture_dimensions():
    assert CAPTURE_W == 640
    assert CAPTURE_H == 360


def test_diff_dimensions():
    assert DIFF_W == 64
    assert DIFF_H == 36
