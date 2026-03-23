"""
humphi/logger.py

Records every UI automation action with full metrics:
- Raw UI tree size (nodes + estimated tokens)
- Filtered element count
- Compressed DSL token count
- Reduction percentage
- What was sent to Groq (prompt)
- What Groq responded (steps)
- Timing for every stage
- Success / failure per step

Logs are written to:
  ~/.humphi/logs/humphi_YYYY-MM-DD.jsonl   (one JSON object per line)

A companion HTML dashboard reads these logs and renders them.
"""

import json
import time
import os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional


LOG_DIR = Path.home() / ".humphi" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today_log_path() -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"humphi_{date_str}.jsonl"


@dataclass
class ActionLog:
    """One complete action cycle logged as a single record."""
    timestamp: str = ""
    session_id: str = ""
    task: str = ""

    # Tree metrics
    raw_node_count: int = 0
    raw_token_estimate: int = 0
    filtered_element_count: int = 0
    dsl_token_count: int = 0
    reduction_percent: float = 0.0

    # Timing (ms)
    filter_time_ms: float = 0.0
    compress_time_ms: float = 0.0
    groq_latency_ms: float = 0.0
    total_time_ms: float = 0.0

    # Payloads
    dsl_payload: str = ""
    groq_prompt: str = ""
    groq_response: str = ""
    steps_planned: list = field(default_factory=list)

    # Execution
    steps_executed: int = 0
    steps_succeeded: int = 0
    steps_failed: int = 0
    execution_errors: list = field(default_factory=list)

    # Outcome
    success: bool = False
    notes: str = ""


class HumphiLogger:
    """
    Centralized logger for Humphi AI UI automation.
    One instance per session. Thread-safe for single-agent use.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current: Optional[ActionLog] = None
        self._session_start = time.perf_counter()
        self._log_path = _today_log_path()

        # Write session start marker
        self._write({
            "type": "session_start",
            "session_id": self.session_id,
            "timestamp": self._now(),
        })

    # ── Public API ────────────────────────────────────────────────────────────

    def begin_action(self, task: str):
        """Call at the start of every new user task."""
        self._current = ActionLog(
            timestamp=self._now(),
            session_id=self.session_id,
            task=task,
        )
        self._action_start = time.perf_counter()

    def log_filter(self, filter_result, task: str):
        """Called by filter.py after filter + compress completes."""
        if not self._current:
            self.begin_action(task)

        self._current.raw_node_count = filter_result.raw_node_count
        self._current.raw_token_estimate = filter_result.raw_token_estimate
        self._current.filtered_element_count = filter_result.filtered_count
        self._current.dsl_token_count = filter_result.dsl_token_estimate
        self._current.reduction_percent = filter_result.reduction_percent
        self._current.filter_time_ms = filter_result.filter_time_ms
        self._current.compress_time_ms = filter_result.compress_time_ms
        self._current.dsl_payload = filter_result.dsl_payload

    def log_groq_request(self, prompt: str):
        """Call just before sending to Groq."""
        if self._current:
            self._current.groq_prompt = prompt
        self._groq_start = time.perf_counter()

    def log_groq_response(self, response: str, steps: list):
        """Call immediately after Groq responds."""
        if self._current:
            self._current.groq_response = response
            self._current.steps_planned = steps
            self._current.groq_latency_ms = round(
                (time.perf_counter() - self._groq_start) * 1000, 2
            )

    def log_step_executed(self, step: dict, success: bool, error: str = ""):
        """Call after each individual UI step executes."""
        if not self._current:
            return
        self._current.steps_executed += 1
        if success:
            self._current.steps_succeeded += 1
        else:
            self._current.steps_failed += 1
            if error:
                self._current.execution_errors.append({
                    "step": step,
                    "error": error
                })

    def finish_action(self, success: bool, notes: str = ""):
        """Call when the full task completes or fails."""
        if not self._current:
            return

        self._current.success = success
        self._current.notes = notes
        self._current.total_time_ms = round(
            (time.perf_counter() - self._action_start) * 1000, 2
        )

        record = asdict(self._current)
        record["type"] = "action"
        self._write(record)

        # Print summary to console in debug mode
        self._print_summary(self._current)

        self._current = None

    def log_error(self, error: str, context: str = ""):
        """Log a standalone error outside of a normal action cycle."""
        self._write({
            "type": "error",
            "session_id": self.session_id,
            "timestamp": self._now(),
            "error": error,
            "context": context,
        })

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write(self, record: dict):
        """Append one JSON record to today's log file."""
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[HumphiLogger] Failed to write log: {e}")

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _print_summary(self, log: ActionLog):
        """Print a clean summary to console after every action."""
        print("\n" + "─" * 60)
        print(f"[HUMPHI] Task: {log.task}")
        print(f"  Raw tree:    {log.raw_node_count} nodes  (~{log.raw_token_estimate} tokens)")
        print(f"  After filter:{log.filtered_element_count} elements")
        print(f"  DSL payload: {log.dsl_token_count} tokens  ({log.reduction_percent}% reduction)")
        print(f"  Filter:      {log.filter_time_ms}ms")
        print(f"  Compress:    {log.compress_time_ms}ms")
        print(f"  Groq:        {log.groq_latency_ms}ms")
        print(f"  Total:       {log.total_time_ms}ms")
        print(f"  Steps:       {log.steps_executed} executed, {log.steps_succeeded} ok, {log.steps_failed} failed")
        print(f"  Result:      {'✓ SUCCESS' if log.success else '✗ FAILED'}")
        print("─" * 60 + "\n")
