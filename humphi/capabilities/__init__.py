"""
humphi/capabilities/__init__.py — Capability Module Loader

Lazy-loads capability modules on demand based on keyword matching.
Only the matched module's prompt is injected into the AI context.

Phase 2: Added direct_commands support for zero-LLM-cost execution.

Architecture:
  - Thin intent router (200 tokens) always loaded
  - Capability modules (JSON files) loaded only when needed
  - Direct commands bypass LLM entirely (~30% of requests)
  - Future: modules served from Bifrost/Redis for speed

Production path:
  Local JSON → Bifrost API → Redis cache → instant lookup
"""

import json
import os
from pathlib import Path

CAPS_DIR = Path(__file__).parent
_module_index = None  # lazy-loaded keyword → module_id map
_module_cache = {}    # module_id → loaded JSON
_direct_cmd_index = None  # phrase → command map (zero LLM cost)

def _build_index():
    """Build keyword → module_id index from JSON files. Done once on first use."""
    global _module_index, _direct_cmd_index
    _module_index = {}
    _direct_cmd_index = {}
    for f in CAPS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            mid = data["id"]
            _module_cache[mid] = data
            for kw in data.get("keywords", []):
                _module_index[kw.lower()] = mid
            # Build direct command index
            for phrase, cmd in data.get("direct_commands", {}).items():
                _direct_cmd_index[phrase.lower()] = cmd
        except: pass


def _ensure_index():
    if _module_index is None:
        _build_index()

def match_capability(user_text: str) -> dict | None:
    """Match user text to a capability module. Returns the module dict or None."""
    _ensure_index()
    text = user_text.lower()
    # Score each module by keyword hits
    scores = {}
    for kw, mid in _module_index.items():
        if kw in text:
            scores[mid] = scores.get(mid, 0) + len(kw)  # longer matches score higher
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return _module_cache.get(best)


def check_direct_command(user_text: str) -> str | None:
    """Check if user text matches a direct command (zero LLM cost).
    Returns the command string to execute, or None.
    Handles ~30% of simple requests like 'open task manager'."""
    _ensure_index()
    text = user_text.lower().strip()
    # Exact match first
    if text in _direct_cmd_index:
        return _direct_cmd_index[text]
    # Fuzzy: check if user text starts with or contains a direct command phrase
    for phrase, cmd in _direct_cmd_index.items():
        if phrase in text and len(phrase) >= 6:  # min 6 chars to avoid false matches
            return cmd
    return None


def get_capability(module_id: str) -> dict | None:
    """Get a specific capability module by ID."""
    _ensure_index()
    return _module_cache.get(module_id)


def list_capabilities() -> list[str]:
    """List all available capability IDs."""
    _ensure_index()
    return list(_module_cache.keys())

def build_context_prompt(module: dict) -> str:
    """Build the injected context for a matched capability.
    Returns a compact prompt with launch commands and domain knowledge."""
    parts = [module["prompt"]]

    # Add available launch commands
    launches = module.get("launch", {})
    if launches:
        cmds = ", ".join(f"{k}: {v}" for k, v in launches.items())
        parts.append(f"LAUNCH COMMANDS: {cmds}")

    # Add available diagnostics
    diags = module.get("diagnostics", [])
    if diags:
        parts.append(f"DIAGNOSTIC COMMANDS (read-only, safe to run): {'; '.join(diags[:3])}")

    return "\n".join(parts)
