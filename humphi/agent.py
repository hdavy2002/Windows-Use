"""
humphi/agent.py

Drop-in integration layer for Windows-Use.

This wraps Windows-Use's Agent class with Humphi AI's:
  1. UI tree filtering
  2. DSL compression
  3. Groq as primary LLM
  4. Full action logging

Usage:
    from humphi.agent import HumphiAgent

    agent = HumphiAgent(groq_api_key="gsk_...")
    agent.run("Create an invoice for Sharma for 50000 in QuickBooks")
"""

import os
import time
import json
from typing import Optional

# Windows-Use imports (already installed in your fork)
try:
    import uiautomation as auto
except ImportError:
    auto = None

from humphi.filter import filter_and_compress
from humphi.groq_provider import HumphiGroqProvider
from humphi.logger import HumphiLogger


class HumphiAgent:
    """
    Humphi AI's Windows automation agent.

    Flow for every task:
    1. Get root window (currently focused or specified)
    2. Filter UI tree to interactive elements only
    3. Compress to DSL format
    4. Send tiny payload to Groq
    5. Execute returned steps using uiautomation
    6. Log everything to ~/.humphi/logs/
    """

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        max_retries: int = 2,
        max_elements: int = 25,
        verbose: bool = True,
    ):
        self.groq = HumphiGroqProvider(
            api_key=groq_api_key or os.environ.get("GROQ_API_KEY", "")
        )
        self.logger = HumphiLogger()
        self.max_retries = max_retries
        self.max_elements = max_elements
        self.verbose = verbose

    def run(self, task: str, window_title: Optional[str] = None) -> bool:
        """
        Run a natural language task on the Windows desktop.

        Args:
            task: plain English description of what to do
            window_title: target window title (uses focused window if None)

        Returns:
            True if task completed successfully, False otherwise
        """
        if not auto:
            print("[HumphiAgent] uiautomation not installed. Run: pip install uiautomation")
            return False

        self.logger.begin_action(task)

        try:
            # ── Step 1: Get root control ──────────────────────────────────
            if window_title:
                root = auto.WindowControl(Name=window_title)
                if not root.Exists(3):  # wait up to 3 seconds
                    self.logger.finish_action(False, f"Window not found: {window_title}")
                    return False
            else:
                root = auto.GetFocusedControl()
                # Walk up to window level
                while root and root.ControlTypeName not in ("Window", "Pane"):
                    root = root.GetParentControl()

            if not root:
                self.logger.finish_action(False, "No active window found")
                return False

            # ── Step 2 & 3: Filter + Compress ────────────────────────────
            filter_result = filter_and_compress(
                root_control=root,
                task=task,
                logger=self.logger,
                max_elements=self.max_elements,
            )

            if filter_result.filtered_count == 0:
                self.logger.finish_action(False, "No interactive elements found on screen")
                return False

            if self.verbose:
                print(f"[Humphi] {filter_result.raw_node_count} nodes → "
                      f"{filter_result.filtered_count} filtered → "
                      f"{filter_result.dsl_token_count} tokens "
                      f"({filter_result.reduction_percent}% reduction)")

            # ── Step 4: Ask Groq ──────────────────────────────────────────
            steps, raw_response, groq_ms = self.groq.plan_steps(
                task=task,
                dsl_payload=filter_result.dsl_payload,
                logger=self.logger,
            )

            if self.verbose:
                print(f"[Humphi] Groq responded in {groq_ms}ms with {len(steps)} steps")

            if not steps:
                self.logger.finish_action(False, f"Groq returned no steps. Raw: {raw_response[:200]}")
                return False

            if len(steps) == 1 and "error" in steps[0]:
                self.logger.finish_action(False, f"Groq error: {steps[0]['error']}")
                return False

            # ── Step 5: Execute steps ─────────────────────────────────────
            success = self._execute_steps(steps, root)

            self.logger.finish_action(success)
            return success

        except Exception as e:
            self.logger.finish_action(False, str(e))
            self.logger.log_error(str(e), context="agent.run")
            if self.verbose:
                print(f"[Humphi] Error: {e}")
            return False

    def _execute_steps(self, steps: list, root) -> bool:
        """Execute each step from Groq's plan against the live UI."""
        for step in steps:
            element_id = step.get("id", "")
            action = step.get("action", "click")
            value = step.get("value", "")

            try:
                # Find element by AutomationId first, then by Name
                element = self._find_element(root, element_id)

                if not element:
                    self.logger.log_step_executed(
                        step, False, f"Element not found: {element_id}"
                    )
                    if self.verbose:
                        print(f"[Humphi] ✗ Element not found: {element_id}")
                    continue

                # Execute the action
                self._do_action(element, action, value)
                self.logger.log_step_executed(step, True)

                if self.verbose:
                    print(f"[Humphi] ✓ {action} on '{element_id}'"
                          + (f" → '{value}'" if value else ""))

                # Small delay between actions — feels more natural
                # and gives the UI time to respond
                time.sleep(0.15)

            except Exception as e:
                self.logger.log_step_executed(step, False, str(e))
                if self.verbose:
                    print(f"[Humphi] ✗ Failed step {step}: {e}")

        return True

    def _find_element(self, root, identifier: str):
        """Find element by AutomationId or Name. Returns first match."""
        if not identifier:
            return None

        # Try AutomationId first — most reliable
        el = root.Control(AutomationId=identifier)
        if el and el.Exists(0.5):
            return el

        # Fall back to Name match
        el = root.Control(Name=identifier)
        if el and el.Exists(0.5):
            return el

        return None

    def _do_action(self, element, action: str, value: str = ""):
        """Execute a single action on a UI element."""
        action = action.lower()

        if action == "click":
            element.Click()

        elif action == "type":
            element.Click()
            time.sleep(0.05)
            # Clear existing content then type
            element.SendKeys("{Ctrl}a", waitTime=0)
            element.SendKeys(value, waitTime=0)

        elif action == "select":
            # ComboBox selection
            element.Click()
            time.sleep(0.1)
            # Try to find the item in dropdown
            item = element.ListItemControl(Name=value)
            if item and item.Exists(1):
                item.Click()
            else:
                # Type it if can't find in list
                element.SendKeys(value)

        elif action == "check":
            if not element.GetTogglePattern().ToggleState:
                element.Click()

        elif action == "focus":
            element.SetFocus()

        elif action == "scroll":
            element.WheelDown(wheelTimes=3)

        else:
            # Default to click
            element.Click()
