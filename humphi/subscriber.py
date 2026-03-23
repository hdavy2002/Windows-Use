"""
humphi/subscriber.py

Hooks into Windows-Use's event system and logs everything to
~/.humphi/logs/humphi_YYYY-MM-DD.jsonl

The HTML monitor (humphi/monitor.html) reads these logs.

Usage — pass to Agent():
    from humphi.subscriber import HumphiEventSubscriber
    subscriber = HumphiEventSubscriber()
    agent = Agent(llm=llm, event_subscriber=subscriber)

Or use the patched main.py which wires this in automatically.
"""

import json
import time
import os
from datetime import datetime
from pathlib import Path
from windows_use.agent.events.views import AgentEvent, EventType

LOG_DIR = Path.home() / ".humphi" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today_log() -> Path:
    return LOG_DIR / f"humphi_{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def _write(record: dict):
    try:
        with open(_today_log(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[HumphiLog] Write error: {e}")


class HumphiEventSubscriber:
    """
    Subscribes to all Windows-Use agent events and writes structured
    logs for the Humphi AI monitor dashboard.

    Tracks per-session:
    - Every thought the agent has
    - Every tool call with parameters
    - Every tool result with success/failure
    - Final done or error outcome
    - Timing for each step
    - Running token estimate based on message sizes
    """

    def __init__(self):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task = ""
        self.step_start = time.perf_counter()
        self.session_start = time.perf_counter()
        self.steps = []
        self.current_step = {}
        self.total_tool_calls = 0
        self.total_failures = 0

        _write({
            "type": "session_start",
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
        })

    def __call__(self, event: AgentEvent):
        """Called by Windows-Use for every agent event."""
        try:
            match event.type:
                case EventType.THOUGHT:
                    self._on_thought(event)
                case EventType.TOOL_CALL:
                    self._on_tool_call(event)
                case EventType.TOOL_RESULT:
                    self._on_tool_result(event)
                case EventType.DONE:
                    self._on_done(event)
                case EventType.ERROR:
                    self._on_error(event)
        except Exception as e:
            print(f"[HumphiLog] Subscriber error: {e}")

    def set_task(self, task: str):
        """Call before agent.invoke() to set the task name for logging."""
        self.task = task
        self.session_start = time.perf_counter()
        self.steps = []
        self.total_tool_calls = 0
        self.total_failures = 0
        _write({
            "type": "task_start",
            "session_id": self.session_id,
            "task": task,
            "timestamp": datetime.now().isoformat(),
        })

    def _on_thought(self, event: AgentEvent):
        step = event.data.get("step", 0)
        thought = event.data.get("thought", "")
        self.step_start = time.perf_counter()
        self.current_step = {
            "step": step,
            "thought": thought,
            "thought_tokens": self._estimate_tokens(thought),
            "timestamp": datetime.now().isoformat(),
        }

    def _on_tool_call(self, event: AgentEvent):
        step = event.data.get("step", 0)
        tool_name = event.data.get("tool_name", "")
        tool_params = event.data.get("tool_params", {})
        self.total_tool_calls += 1

        self.current_step.update({
            "tool_name": tool_name,
            "tool_params": tool_params,
            "tool_params_tokens": self._estimate_tokens(json.dumps(tool_params)),
        })

        _write({
            "type": "tool_call",
            "session_id": self.session_id,
            "task": self.task,
            "step": step,
            "tool_name": tool_name,
            "tool_params": tool_params,
            "timestamp": datetime.now().isoformat(),
        })

    def _on_tool_result(self, event: AgentEvent):
        step = event.data.get("step", 0)
        tool_name = event.data.get("tool_name", "")
        is_success = event.data.get("is_success", False)
        content = event.data.get("content", "")
        elapsed = round((time.perf_counter() - self.step_start) * 1000, 1)

        if not is_success:
            self.total_failures += 1

        self.current_step.update({
            "is_success": is_success,
            "result_preview": str(content)[:200],
            "result_tokens": self._estimate_tokens(str(content)),
            "step_time_ms": elapsed,
        })

        self.steps.append(dict(self.current_step))

        _write({
            "type": "tool_result",
            "session_id": self.session_id,
            "task": self.task,
            "step": step,
            "tool_name": tool_name,
            "is_success": is_success,
            "result_preview": str(content)[:200],
            "step_time_ms": elapsed,
            "timestamp": datetime.now().isoformat(),
        })

    def _on_done(self, event: AgentEvent):
        step = event.data.get("step", 0)
        content = event.data.get("content", "")
        total_time = round((time.perf_counter() - self.session_start) * 1000, 1)

        record = {
            "type": "action",
            "session_id": self.session_id,
            "task": self.task,
            "success": True,
            "total_steps": step + 1,
            "total_tool_calls": self.total_tool_calls,
            "total_failures": self.total_failures,
            "total_time_ms": total_time,
            "result": str(content)[:500],
            "steps": self.steps,
            "timestamp": datetime.now().isoformat(),
            # Token estimates
            "estimated_tokens_per_step": self._avg_tokens_per_step(),
            "estimated_total_tokens": self._avg_tokens_per_step() * (step + 1),
        }
        _write(record)
        self._print_summary(record)

    def _on_error(self, event: AgentEvent):
        step = event.data.get("step", 0)
        error = event.data.get("error", "")
        total_time = round((time.perf_counter() - self.session_start) * 1000, 1)

        record = {
            "type": "action",
            "session_id": self.session_id,
            "task": self.task,
            "success": False,
            "total_steps": step + 1,
            "total_tool_calls": self.total_tool_calls,
            "total_failures": self.total_failures,
            "total_time_ms": total_time,
            "error": error,
            "steps": self.steps,
            "timestamp": datetime.now().isoformat(),
            "estimated_tokens_per_step": self._avg_tokens_per_step(),
            "estimated_total_tokens": self._avg_tokens_per_step() * (step + 1),
        }
        _write(record)
        self._print_summary(record)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate — 1 token per 4 characters."""
        return max(1, len(str(text)) // 4)

    def _avg_tokens_per_step(self) -> int:
        if not self.steps:
            return 0
        total = sum(
            s.get("thought_tokens", 0) +
            s.get("tool_params_tokens", 0) +
            s.get("result_tokens", 0)
            for s in self.steps
        )
        return total // len(self.steps)

    def _print_summary(self, record: dict):
        status = "SUCCESS" if record.get("success") else "FAILED"
        print(f"\n{'─'*55}")
        print(f"[HUMPHI] Task: {record.get('task', '')}")
        print(f"  Status:     {status}")
        print(f"  Steps:      {record.get('total_steps', 0)}")
        print(f"  Tool calls: {record.get('total_tool_calls', 0)}")
        print(f"  Failures:   {record.get('total_failures', 0)}")
        print(f"  Time:       {record.get('total_time_ms', 0)}ms")
        print(f"  Est tokens: ~{record.get('estimated_total_tokens', 0)}")
        print(f"  Log:        {_today_log()}")
        print(f"{'─'*55}\n")
