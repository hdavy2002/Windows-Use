"""
humphi/memory.py — Lightweight per-session memory store

Tracks session context for smarter AI responses.
Designed for Cloudflare KV-compatible interface (dict-like get/set/to_prompt).

Storage: ~/.humphi/memory.json
Max context injection: ~2KB / ~120 tokens
"""

import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path.home() / ".humphi" / "memory.json"


class SessionMemory:
    """Per-session memory store for Humphi AI."""

    def __init__(self):
        self._data = {
            "last_task": "",
            "last_action": "",
            "last_capability": "",
            "user_type": "unknown",     # beginner / intermediate / advanced
            "session_count": 0,
            "actions_run": 0,
            "common_intents": {},       # intent → count
        }
        self._load()

    def _load(self):
        """Load persistent memory from disk."""
        try:
            if MEMORY_FILE.exists():
                saved = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                # Merge saved data (keep new keys from defaults)
                for k in self._data:
                    if k in saved:
                        self._data[k] = saved[k]
                # Increment session count
                self._data["session_count"] = saved.get("session_count", 0) + 1
        except:
            pass

    def _save(self):
        """Persist memory to disk."""
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            MEMORY_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except:
            pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def update_after_turn(self, intent: str, capability: str | None, action: dict | None):
        """Update memory after each chat turn."""
        self._data["last_task"] = intent
        if capability:
            self._data["last_capability"] = capability
        if action:
            self._data["last_action"] = json.dumps(action)
            self._data["actions_run"] = self._data.get("actions_run", 0) + 1

        # Track common intents
        intents = self._data.get("common_intents", {})
        intents[intent] = intents.get(intent, 0) + 1
        self._data["common_intents"] = intents

        # Infer user type from session count and actions
        sessions = self._data.get("session_count", 0)
        actions = self._data.get("actions_run", 0)
        if sessions >= 10 or actions >= 20:
            self._data["user_type"] = "advanced"
        elif sessions >= 3 or actions >= 5:
            self._data["user_type"] = "intermediate"
        else:
            self._data["user_type"] = "beginner"

        self._save()

    def to_prompt(self) -> str:
        """Generate a compact memory context for LLM injection (~50 tokens)."""
        parts = []
        if self._data.get("last_task"):
            parts.append(f"Last task: {self._data['last_task']}")
        if self._data.get("last_capability"):
            parts.append(f"Last module: {self._data['last_capability']}")
        if self._data.get("user_type", "unknown") != "unknown":
            parts.append(f"User level: {self._data['user_type']}")

        # Top 3 common intents
        intents = self._data.get("common_intents", {})
        if intents:
            top = sorted(intents, key=intents.get, reverse=True)[:3]
            parts.append(f"Frequent: {', '.join(top)}")

        return "; ".join(parts) if parts else ""

    def get_top_intents(self, n: int = 3) -> list[str]:
        """Return top N most common intent categories for quick-action chip ranking."""
        intents = self._data.get("common_intents", {})
        return sorted(intents, key=intents.get, reverse=True)[:n]
