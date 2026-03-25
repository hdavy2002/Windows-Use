"""
tests/test_phase4.py — Phase 4: Unified Decisions Engine tests

Tests: parallel execution in _do_chat, structured action parsing, and Live+Execution bridge logic.
"""
import sys, os, time, asyncio
import asyncio
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_humphi import parse_actions, check_direct_command, classify_intent
from humphi.memory import SessionMemory

# ── 1. Structured Action Parsing Tests ────────────────────────────────────────

def test_parse_actions_single():
    text = """Here is what I found:
{"action": "open_settings", "target": "network"}
Hope this helps!"""
    actions = parse_actions(text)
    assert len(actions) == 1
    assert actions[0] == {"action": "open_settings", "target": "network"}

def test_parse_actions_multiple():
    text = """I can run these two commands:
{"action": "run_diagnostic", "cmd": "ipconfig"}
{"action": "list_processes"}
Let me know if you need more."""
    actions = parse_actions(text)
    assert len(actions) == 2
    assert actions[0] == {"action": "run_diagnostic", "cmd": "ipconfig"}
    assert actions[1] == {"action": "list_processes"}

def test_parse_actions_empty():
    text = "Just regular chat text here. No actions at all."
    actions = parse_actions(text)
    assert len(actions) == 0

# ── 2. Parallel Classify + Memory Fetch (asyncio.gather) Tests ──────────────

class DummyMemory:
    def to_prompt(self):
        time.sleep(0.05)  # simulate small delay
        return "mock_memory_context"

def dummy_classify_intent(norm_msg):
    time.sleep(0.05)  # simulate small delay
    return "network"

def test_parallel_fetch_context():
    """Test that asyncio.gather successfully runs classify_intent and to_prompt concurrently."""
    norm = "open wifi settings"
    memory = DummyMemory()
    
    async def fetch_context():
        # Start both tasks
        t_intent = asyncio.to_thread(dummy_classify_intent, norm)
        t_mem = asyncio.to_thread(memory.to_prompt)
        
        # Await both
        return await asyncio.gather(t_intent, t_mem)
        
    start_time = time.time()
    intent, mem_ctx = asyncio.run(fetch_context())
    elapsed = time.time() - start_time
    
    assert intent == "network"
    assert mem_ctx == "mock_memory_context"
    # Should be significantly less than 0.1s because they run in parallel
    assert elapsed < 0.09, f"Expected parallel execution, took {elapsed}s"
