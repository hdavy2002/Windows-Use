"""
humphi/filter.py

Filters the raw Windows UI Automation tree down to only
interactive elements, then compresses them into a minimal
DSL format before sending to Groq.

Pipeline:
  Raw UI tree (400+ nodes)
      ↓ filter()       — removes disabled, invisible, structural noise
  Relevant elements (15-20 nodes)
      ↓ compress()     — converts to single-line DSL tokens
  Tiny payload (40-60 tokens)
      ↓ → Groq
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from humphi.logger import HumphiLogger

# ─── Type codes for DSL compression ───────────────────────────────────────────
# Every control type gets a 1-2 char code.
# Groq is trained on language — short codes are still readable in context.
TYPE_CODES = {
    "Button":        "B",
    "Edit":          "E",
    "ComboBox":      "C",
    "CheckBox":      "X",
    "RadioButton":   "R",
    "MenuItem":      "M",
    "TabItem":       "T",
    "ListItem":      "L",
    "Slider":        "SL",
    "Hyperlink":     "H",
    "TreeItem":      "TR",
    "DataItem":      "D",
    "Spinner":       "SP",
    "ToggleButton":  "TB",
    "SplitButton":   "SB",
}

# ─── Control types that are purely structural or decorative ───────────────────
# We never send these to Groq. They hold other elements but are not
# themselves interactable.
SKIP_TYPES = {
    "Pane",
    "Group",
    "Separator",
    "ScrollBar",
    "TitleBar",
    "MenuBar",
    "ToolBar",
    "StatusBar",
    "Image",
    "Text",
    "Custom",
    "Window",        # top level window — recurse into it, don't send it
    "Document",      # document container — recurse into it
    "Header",
    "HeaderItem",
    "Table",         # recurse into rows/cells
    "Tree",          # recurse into tree items
    "List",          # recurse into list items
    "Tab",           # recurse into tab items
    "ToolTip",
    "ProgressBar",   # informational, not interactive
    "Calendar",      # complex — handle separately if needed
}


@dataclass
class UIElement:
    """Minimal representation of a single interactive UI element."""
    control_type: str
    name: str
    automation_id: str
    class_name: str
    is_enabled: bool
    bounding_rect: Optional[tuple] = None  # (x, y, w, h) — kept for fallback

    def dsl(self) -> str:
        """
        Compress to single DSL token.
        Format: TypeCode:automation_id="Name"
        If no automation_id, use name as identifier.
        Example: B:saveClose="Save & Close"
        """
        code = TYPE_CODES.get(self.control_type, "?")
        identifier = self.automation_id or self.name.replace(" ", "_")[:20]
        name = self.name[:40] if self.name else identifier
        return f'{code}:{identifier}="{name}"'

    def token_estimate(self) -> int:
        """Rough token count for this element in DSL format."""
        return max(1, len(self.dsl()) // 4)


@dataclass
class FilterResult:
    """
    Full result from a filter + compress operation.
    Everything the logger needs to record metrics.
    """
    # Raw stats
    raw_node_count: int = 0
    raw_token_estimate: int = 0

    # After filter
    filtered_elements: list = field(default_factory=list)
    filtered_count: int = 0
    filter_time_ms: float = 0.0

    # After compress
    dsl_payload: str = ""
    dsl_token_estimate: int = 0
    compress_time_ms: float = 0.0

    # Reduction metrics
    @property
    def reduction_percent(self) -> float:
        if self.raw_token_estimate == 0:
            return 0.0
        return round(
            (1 - self.dsl_token_estimate / self.raw_token_estimate) * 100, 1
        )


def _count_nodes(control, depth=0, max_depth=12) -> int:
    """Count total nodes in raw tree for metrics only."""
    if depth > max_depth:
        return 0
    count = 1
    try:
        for child in control.GetChildren():
            count += _count_nodes(child, depth + 1, max_depth)
    except Exception:
        pass
    return count


def _should_include(control) -> bool:
    """
    Decide whether this element should be sent to Groq.
    Returns True only for enabled, visible, named, interactive elements.
    """
    try:
        # Skip non-interactive structural types
        if control.ControlTypeName in SKIP_TYPES:
            return False

        # Skip if not in our known interactive types
        if control.ControlTypeName not in TYPE_CODES:
            return False

        # Skip disabled elements — can't interact with them right now
        if not control.IsEnabled:
            return False

        # Skip offscreen elements — not visible to user
        if control.IsOffscreen:
            return False

        # Skip elements with no name AND no automation id
        # Groq has nothing to reference them by
        if not control.Name and not control.AutomationId:
            return False

        # Skip zero-size elements — hidden in tree but not visible
        rect = control.BoundingRectangle
        if rect and (rect.width() <= 0 or rect.height() <= 0):
            return False

        return True

    except Exception:
        return False


def _extract_elements(control, elements: list, depth=0, max_depth=12):
    """
    Recursively walk the UI tree.
    Collect elements that pass _should_include().
    Always recurse into structural containers even when skipping them.
    """
    if depth > max_depth:
        return

    try:
        if _should_include(control):
            rect = control.BoundingRectangle
            elements.append(UIElement(
                control_type=control.ControlTypeName,
                name=control.Name or "",
                automation_id=control.AutomationId or "",
                class_name=control.ClassName or "",
                is_enabled=control.IsEnabled,
                bounding_rect=(
                    (rect.left, rect.top, rect.width(), rect.height())
                    if rect else None
                )
            ))

        # Always recurse — structural containers hold interactive children
        for child in control.GetChildren():
            _extract_elements(child, elements, depth + 1, max_depth)

    except Exception:
        pass


def _score_relevance(element: UIElement, task: str) -> int:
    """
    Simple keyword overlap score between task words and element text.
    Higher score = more relevant to current task.
    Buttons always get a baseline score — they're almost always relevant.
    """
    task_words = set(task.lower().split())
    el_text = (element.name + " " + element.automation_id).lower()
    el_words = set(el_text.replace("_", " ").split())

    score = len(task_words & el_words)

    # Buttons are almost always needed — boost them
    if element.control_type == "Button":
        score += 1

    return score


def filter_and_compress(
    root_control,
    task: str,
    logger: HumphiLogger,
    max_elements: int = 25,
) -> FilterResult:
    """
    Main entry point.

    1. Count raw tree for metrics
    2. Filter to interactive elements only
    3. Score by relevance to task
    4. Compress to DSL format
    5. Log everything

    Args:
        root_control: uiautomation Control object (root window)
        task: user's natural language task string
        logger: HumphiLogger instance
        max_elements: cap on elements sent to Groq (default 25)

    Returns:
        FilterResult with full metrics and DSL payload
    """
    result = FilterResult()

    # ── Step 1: Count raw tree ────────────────────────────────────────────────
    t0 = time.perf_counter()
    result.raw_node_count = _count_nodes(root_control)
    # Rough token estimate: raw tree verbose XML is ~10 tokens per node
    result.raw_token_estimate = result.raw_node_count * 10

    # ── Step 2: Filter ───────────────────────────────────────────────────────
    elements = []
    _extract_elements(root_control, elements)
    result.filter_time_ms = round((time.perf_counter() - t0) * 1000, 2)
    result.filtered_count = len(elements)
    result.filtered_elements = elements

    # ── Step 3: Score relevance and cap ──────────────────────────────────────
    if task:
        scored = sorted(
            elements,
            key=lambda el: _score_relevance(el, task),
            reverse=True
        )
    else:
        scored = elements

    top_elements = scored[:max_elements]

    # ── Step 4: Compress to DSL ───────────────────────────────────────────────
    t1 = time.perf_counter()
    dsl_lines = [el.dsl() for el in top_elements]
    result.dsl_payload = "\n".join(dsl_lines)
    result.dsl_token_estimate = sum(el.token_estimate() for el in top_elements)
    result.compress_time_ms = round((time.perf_counter() - t1) * 1000, 2)

    # ── Step 5: Log everything ────────────────────────────────────────────────
    logger.log_filter(result, task)

    return result
