"""
tests/test_capabilities.py — Capability module tests
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humphi.capabilities import (
    match_capability, build_context_prompt, check_direct_command, list_capabilities
)


def test_all_modules_load():
    """All capability JSON modules should load without errors."""
    caps = list_capabilities()
    assert len(caps) >= 11, f"Expected at least 11 modules, got {len(caps)}: {caps}"


def test_required_modules_present():
    """All required module IDs should be present."""
    caps = list_capabilities()
    required = ["network", "bluetooth", "apps", "system_health", "files",
                "display", "updates", "sound", "printer", "accounts", "privacy"]
    for mid in required:
        assert mid in caps, f"Missing module: {mid}"


def test_keyword_match_network():
    cap = match_capability("my wifi is not working")
    assert cap is not None
    assert cap["id"] == "network"


def test_keyword_match_bluetooth():
    cap = match_capability("pair my bluetooth headphones")
    assert cap is not None
    assert cap["id"] == "bluetooth"


def test_keyword_match_system_health():
    cap = match_capability("my computer is running slow")
    assert cap is not None
    assert cap["id"] == "system_health"


def test_keyword_match_printer():
    cap = match_capability("my printer is not printing")
    assert cap is not None
    assert cap["id"] == "printer"


def test_keyword_match_accounts():
    cap = match_capability("change my password")
    assert cap is not None
    assert cap["id"] == "accounts"


def test_keyword_match_privacy():
    cap = match_capability("change camera permissions")
    assert cap is not None
    assert cap["id"] == "privacy"


def test_no_match_random():
    cap = match_capability("tell me a joke")
    assert cap is None


def test_build_context_prompt():
    cap = match_capability("wifi issue")
    assert cap is not None
    ctx = build_context_prompt(cap)
    assert len(ctx) > 0
    assert "LAUNCH COMMANDS" in ctx or "DIAGNOSTIC" in ctx


def test_modules_have_version():
    """All modules should have version field (Phase 2 upgrade)."""
    from humphi.capabilities import _ensure_index, _module_cache
    _ensure_index()
    for mid, mod in _module_cache.items():
        assert "version" in mod, f"Module '{mid}' missing version"


def test_modules_have_direct_commands():
    """All modules should have direct_commands field (Phase 2 upgrade)."""
    from humphi.capabilities import _ensure_index, _module_cache
    _ensure_index()
    for mid, mod in _module_cache.items():
        assert "direct_commands" in mod, f"Module '{mid}' missing direct_commands"
        assert isinstance(mod["direct_commands"], dict)


# ── Direct Command Tests ──────────────────────────────────────────────────────

def test_direct_command_open_task_manager():
    cmd = check_direct_command("open task manager")
    assert cmd is not None
    assert "taskmgr" in cmd.lower()


def test_direct_command_open_bluetooth():
    cmd = check_direct_command("open bluetooth")
    assert cmd is not None
    assert "bluetooth" in cmd.lower()


def test_direct_command_open_wifi():
    cmd = check_direct_command("open wifi settings")
    assert cmd is not None
    assert "wifi" in cmd.lower()


def test_direct_command_no_match():
    cmd = check_direct_command("tell me about the weather")
    assert cmd is None


def test_direct_command_case_insensitive():
    cmd = check_direct_command("OPEN TASK MANAGER")
    assert cmd is not None
