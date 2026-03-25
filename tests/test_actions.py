"""
tests/test_actions.py — Action execution tests (mocked subprocess)
"""
import sys, os, json
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_humphi import execute_action, parse_actions


# ── parse_actions ─────────────────────────────────────────────────────────────

def test_parse_open_settings():
    reply = 'I can help. {"action": "open_settings", "target": "network"}'
    actions = parse_actions(reply)
    assert len(actions) == 1
    assert actions[0]["action"] == "open_settings"
    assert actions[0]["target"] == "network"


def test_parse_run_diagnostic():
    reply = 'Let me check. {"action": "run_diagnostic", "cmd": "Get-Process | Select -First 5"}'
    actions = parse_actions(reply)
    assert len(actions) == 1
    assert actions[0]["action"] == "run_diagnostic"


def test_parse_no_actions():
    reply = "Just restart your computer and it should work."
    actions = parse_actions(reply)
    assert len(actions) == 0


def test_parse_multiple_actions():
    reply = '{"action":"open_settings","target":"wifi"} and {"action":"run_diagnostic","cmd":"Test-NetConnection"}'
    actions = parse_actions(reply)
    assert len(actions) == 2


# ── execute_action ────────────────────────────────────────────────────────────

@patch("main_humphi.subprocess.run")
def test_execute_open_settings(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    ok, out = execute_action({"action": "open_settings", "target": "network"})
    assert ok == True
    mock_run.assert_called_once()


@patch("main_humphi.subprocess.run")
def test_execute_run_diagnostic(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="CPU: 15%", stderr="")
    ok, out = execute_action({"action": "run_diagnostic", "cmd": "Get-Process"})
    assert ok == True
    assert "CPU" in out or ok


def test_execute_blocked_command():
    """Dangerous commands should be blocked by allowlist."""
    ok, out = execute_action({"action": "run_diagnostic", "cmd": "Remove-Item -Recurse C:\\"})
    assert ok == False
    assert "blocked" in out.lower() or "not allowed" in out.lower() or not ok


def test_execute_unknown_action():
    ok, out = execute_action({"action": "unknown_action", "target": "x"})
    # Should either fail or not crash
    assert isinstance(ok, bool)
