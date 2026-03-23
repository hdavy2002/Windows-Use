"""
humphi/agent.py
"""

import os
import time
from typing import Optional

try:
    import uiautomation as auto
except ImportError:
    auto = None

from humphi.filter import filter_and_compress
from humphi.groq_provider import HumphiGroqProvider
from humphi.logger import HumphiLogger


class HumphiAgent:

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
        if not auto:
            print("[HumphiAgent] uiautomation not installed. Run: pip install uiautomation")
            return False

        self.logger.begin_action(task)

        try:
            # ── Step 1: Find window ───────────────────────────────────────
            root = None

            if window_title:
                root = self._find_window_by_title(window_title)
                if not root:
                    print(f"[Humphi] Window not found: '{window_title}'")
                    print("[Humphi] Available windows:")
                    self._list_windows()
                    self.logger.finish_action(False, f"Window not found: {window_title}")
                    return False
            else:
                # No title given — try focused control, walk up to Window
                try:
                    focused = auto.GetFocusedControl()
                    if focused:
                        root = focused
                        for _ in range(10):
                            if root.ControlTypeName == "Window":
                                break
                            parent = root.GetParentControl()
                            if not parent or parent.ControlTypeName == "Pane":
                                break
                            root = parent
                except Exception:
                    pass

            if not root:
                print("[Humphi] No window found. Pass window_title= explicitly.")
                self._list_windows()
                self.logger.finish_action(False, "No window found")
                return False

            print(f"[Humphi] Target window: '{root.Name}' [{root.ControlTypeName}]")

            # ── Step 2 & 3: Filter + Compress ────────────────────────────
            filter_result = filter_and_compress(
                root_control=root,
                task=task,
                logger=self.logger,
                max_elements=self.max_elements,
            )

            if filter_result.filtered_count == 0:
                print("[Humphi] No interactive elements found. Dumping raw tree:")
                self._debug_tree(root)
                self.logger.finish_action(False, "No interactive elements found")
                return False

            if self.verbose:
                print(f"[Humphi] {filter_result.raw_node_count} nodes → "
                      f"{filter_result.filtered_count} filtered → "
                      f"{filter_result.dsl_token_count} tokens "
                      f"({filter_result.reduction_percent}% reduction)")
                print(f"[Humphi] DSL payload:\n{filter_result.dsl_payload}\n")

            # ── Step 4: Ask Groq ──────────────────────────────────────────
            steps, raw_response, groq_ms = self.groq.plan_steps(
                task=task,
                dsl_payload=filter_result.dsl_payload,
                logger=self.logger,
            )

            if self.verbose:
                print(f"[Humphi] Groq responded in {groq_ms}ms")
                print(f"[Humphi] Groq raw response: {raw_response}")
                print(f"[Humphi] Steps planned: {steps}")

            if not steps:
                self.logger.finish_action(False, f"Groq returned no steps. Raw: {raw_response[:200]}")
                return False

            if len(steps) == 1 and "error" in steps[0]:
                self.logger.finish_action(False, f"Groq error: {steps[0]['error']}")
                return False

            # ── Step 5: Execute ───────────────────────────────────────────
            success = self._execute_steps(steps, root)
            self.logger.finish_action(success)
            return success

        except Exception as e:
            self.logger.finish_action(False, str(e))
            self.logger.log_error(str(e), context="agent.run")
            import traceback
            print(f"[Humphi] Error: {e}")
            traceback.print_exc()
            return False

    def _find_window_by_title(self, title: str):
        """
        Find a top-level window by partial title match.
        Notepad's title is 'Untitled - Notepad' not just 'Notepad'.
        So partial match is essential.
        """
        try:
            desktop = auto.GetRootControl()
            for win in desktop.GetChildren():
                win_name = win.Name or ""
                if title.lower() in win_name.lower():
                    return win
        except Exception as e:
            print(f"[Humphi] Error finding window: {e}")
        return None

    def _list_windows(self):
        """Print all visible top-level windows for debugging."""
        try:
            desktop = auto.GetRootControl()
            for win in desktop.GetChildren():
                if win.Name:
                    print(f"  [{win.ControlTypeName}] '{win.Name}'")
        except Exception:
            pass

    def _debug_tree(self, root, depth=0, max_depth=4):
        """Print raw tree for debugging when filter finds nothing."""
        if depth > max_depth:
            return
        try:
            indent = "  " * depth
            print(f"{indent}[{root.ControlTypeName}] '{root.Name}' "
                  f"id='{root.AutomationId}' enabled={root.IsEnabled}")
            for child in root.GetChildren():
                self._debug_tree(child, depth + 1, max_depth)
        except Exception:
            pass

    def _execute_steps(self, steps: list, root) -> bool:
        for step in steps:
            element_id = step.get("id", "")
            action = step.get("action", "click")
            value = step.get("value", "")

            try:
                element = self._find_element(root, element_id)

                if not element:
                    self.logger.log_step_executed(step, False, f"Element not found: {element_id}")
                    if self.verbose:
                        print(f"[Humphi] ✗ Element not found: {element_id}")
                    continue

                self._do_action(element, action, value)
                self.logger.log_step_executed(step, True)

                if self.verbose:
                    print(f"[Humphi] ✓ {action} '{element_id}'" + (f" = '{value}'" if value else ""))

                time.sleep(0.15)

            except Exception as e:
                self.logger.log_step_executed(step, False, str(e))
                print(f"[Humphi] ✗ Step failed {step}: {e}")

        return True

    def _find_element(self, root, identifier: str):
        if not identifier:
            return None

        try:
            el = root.Control(AutomationId=identifier)
            if el and el.Exists(0.5):
                return el
        except Exception:
            pass

        try:
            el = root.Control(Name=identifier)
            if el and el.Exists(0.5):
                return el
        except Exception:
            pass

        return None

    def _do_action(self, element, action: str, value: str = ""):
        action = action.lower()

        if action == "click":
            element.Click()

        elif action == "type":
            element.Click()
            time.sleep(0.1)
            element.SendKeys("{Ctrl}a", waitTime=0)
            element.SendKeys(value, waitTime=0)

        elif action == "select":
            element.Click()
            time.sleep(0.15)
            item = element.ListItemControl(Name=value)
            if item and item.Exists(1):
                item.Click()
            else:
                element.SendKeys(value)

        elif action == "check":
            element.Click()

        elif action == "focus":
            element.SetFocus()

        else:
            element.Click()