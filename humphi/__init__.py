"""
Humphi AI — Windows Use Enhancement Layer

Adds to Windows-Use:
- UI tree filtering (remove noise before sending to LLM)
- DSL compression (40-60 tokens vs 4000+ raw tokens)
- Groq as primary LLM (fastest available, ~200ms latency)
- Full action logging with metrics
- HTML monitoring dashboard

Quick start:
    from humphi.agent import HumphiAgent
    agent = HumphiAgent(groq_api_key="gsk_...")
    agent.run("Open Notepad and type Hello World")
"""

from humphi.agent import HumphiAgent
from humphi.filter import filter_and_compress, FilterResult
from humphi.groq_provider import HumphiGroqProvider
from humphi.logger import HumphiLogger

__version__ = "0.1.0"
__all__ = ["HumphiAgent", "filter_and_compress", "FilterResult", "HumphiGroqProvider", "HumphiLogger"]
