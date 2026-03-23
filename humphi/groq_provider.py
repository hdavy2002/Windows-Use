"""
humphi/groq_provider.py

Groq as the primary LLM for Humphi AI's Windows UI automation.

Groq is chosen because:
- Time to first token: ~200ms (fastest available)
- Throughput: 800+ tokens/second
- Cost: ~$0.06 per million tokens
- No local RAM needed
- Llama 3.1 8B handles structured JSON decisions perfectly

This module wraps the Groq API for UI step planning.
It takes a DSL payload + task and returns a list of executable steps.
"""

import json
import os
import time
from typing import Optional
from groq import Groq

# Default model — fast, cheap, handles structured output well
GROQ_MODEL = "llama-3.1-8b-instant"

# System prompt — very short, very focused
# We tell it exactly what format to return
# No general conversation ability needed here
SYSTEM_PROMPT = """You are a Windows UI automation planner.
You receive:
1. A task in plain English
2. A list of available UI elements in DSL format:
   B=Button, E=Edit field, C=ComboBox, X=CheckBox, R=RadioButton,
   M=MenuItem, T=TabItem, L=ListItem, SL=Slider, H=Hyperlink

Format: TypeCode:automation_id="Label"

Return ONLY a JSON array of steps. No explanation. No markdown.
Each step: {"id": "automation_id", "action": "click|type|select|check", "value": "text if needed"}

If a step requires typing, include the value.
If clicking only, omit value.
If the task cannot be completed with available elements, return: {"error": "reason"}
"""


class HumphiGroqProvider:
    """
    Wraps Groq API for UI step planning.
    One instance per session.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = GROQ_MODEL):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model
        self.client = Groq(api_key=self.api_key)

    def plan_steps(
        self,
        task: str,
        dsl_payload: str,
        logger=None,
    ) -> tuple[list, str, float]:
        """
        Send filtered DSL payload + task to Groq.
        Returns (steps_list, raw_response, latency_ms)

        Args:
            task: user's natural language request
            dsl_payload: compressed DSL from filter.py
            logger: HumphiLogger instance (optional)

        Returns:
            steps: list of step dicts ready for execution
            raw_response: raw string from Groq
            latency_ms: round trip time in milliseconds
        """

        # Build the minimal prompt
        user_message = f"Task: {task}\n\nUI elements:\n{dsl_payload}"

        if logger:
            logger.log_groq_request(user_message)

        t0 = time.perf_counter()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,      # deterministic — we want reliable JSON
                max_tokens=512,       # steps list never needs more than this
                response_format={"type": "json_object"},  # enforce JSON output
            )

            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            raw = response.choices[0].message.content

            steps = self._parse_steps(raw)

            if logger:
                logger.log_groq_response(raw, steps)

            return steps, raw, latency_ms

        except Exception as e:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            error_msg = str(e)

            if logger:
                logger.log_groq_response(f"ERROR: {error_msg}", [])
                logger.log_error(error_msg, context="groq_plan_steps")

            return [], error_msg, latency_ms

    def _parse_steps(self, raw: str) -> list:
        """
        Parse Groq's JSON response into a clean list of steps.
        Handles both array response and object with steps key.
        """
        try:
            parsed = json.loads(raw)

            # Groq sometimes returns {"steps": [...]} or {"actions": [...]}
            if isinstance(parsed, dict):
                for key in ("steps", "actions", "plan", "result"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                # Check for error
                if "error" in parsed:
                    return [{"error": parsed["error"]}]
                return []

            if isinstance(parsed, list):
                return parsed

            return []

        except json.JSONDecodeError:
            # Try to extract JSON array from raw string if model added text
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            return []
