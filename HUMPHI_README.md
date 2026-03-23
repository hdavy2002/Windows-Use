# Humphi AI — Windows-Use Enhancement Layer

This fork adds a speed and observability layer on top of [Windows-Use](https://github.com/CursorTouch/Windows-Use).

## What Changed

### The Problem with Original Windows-Use
Every step sends the **full raw UI tree** to the LLM. A typical Windows app has 300-400 nodes. In verbose XML format that's ~4000 tokens per LLM call. With multiple steps per task, costs and latency add up fast.

### Humphi's Solution: Filter → Compress → Groq

```
Raw UI tree (400 nodes, ~4000 tokens)
    ↓ filter()       — removes disabled, invisible, structural noise
Interactive elements (15-20 nodes)
    ↓ compress()     — converts to single-line DSL tokens
Tiny DSL payload (40-60 tokens)
    ↓ Groq           — ~200ms latency, $0.06/million tokens
JSON steps back
    ↓ Execute
```

**Typical result: 80-95% token reduction. Sub-300ms Groq response.**

## New Files

```
humphi/
├── __init__.py         # Package entry point
├── agent.py            # HumphiAgent — drop-in replacement
├── filter.py           # UI tree filter + DSL compressor
├── groq_provider.py    # Groq integration (primary LLM)
├── logger.py           # Full action logging with metrics
└── monitor.html        # Monitoring dashboard (open in browser)
```

## Quick Start

### 1. Install dependencies

```bash
pip install groq uiautomation
```

### 2. Set your Groq API key

```bash
# Get your free key at console.groq.com
export GROQ_API_KEY=gsk_your_key_here
```

### 3. Run a task

```python
from humphi.agent import HumphiAgent

agent = HumphiAgent()
agent.run("Create an invoice for Sharma for 50000 in QuickBooks")
```

### 4. Monitor performance

Open `humphi/monitor.html` in your browser.
Load the log file from `~/.humphi/logs/humphi_YYYY-MM-DD.jsonl`

You'll see for every action:
- Raw tree size vs what was actually sent to Groq
- Token reduction percentage
- Groq latency
- Step-by-step execution results
- Full DSL payload and Groq response

## DSL Format

The compressed format sent to Groq:

```
B:saveClose="Save & Close"       # Button
E:customerName="Customer Name"   # Edit field
C:statusCombo="Status"           # ComboBox
X:rememberMe="Remember Me"       # CheckBox
M:fileNew="New Document"         # MenuItem
```

Type codes: B=Button, E=Edit, C=ComboBox, X=CheckBox, R=RadioButton,
M=MenuItem, T=TabItem, L=ListItem, SL=Slider, H=Hyperlink

## Groq Model

Default: `llama-3.1-8b-instant`

- ~200ms time to first token
- 800+ tokens/second throughput  
- $0.06 per million tokens
- Perfect for structured JSON step planning

Change model in `humphi/groq_provider.py`:
```python
GROQ_MODEL = "llama-3.3-70b-versatile"  # more capable, slightly slower
```

## Logs

Every action is logged to `~/.humphi/logs/humphi_YYYY-MM-DD.jsonl`

Each record contains:
```json
{
  "task": "Create invoice for Sharma",
  "raw_node_count": 342,
  "raw_token_estimate": 3420,
  "filtered_element_count": 18,
  "dsl_token_count": 52,
  "reduction_percent": 98.5,
  "filter_time_ms": 12.3,
  "compress_time_ms": 1.1,
  "groq_latency_ms": 187.4,
  "total_time_ms": 324.8,
  "dsl_payload": "C:customerCombo=\"Customer Job\"\nE:amount=\"Amount\"\nB:saveClose=\"Save & Close\"",
  "groq_response": "[{\"id\":\"customerCombo\",\"action\":\"select\",\"value\":\"Sharma\"}...]",
  "steps_planned": [...],
  "steps_executed": 3,
  "steps_succeeded": 3,
  "steps_failed": 0,
  "success": true
}
```

## Original Windows-Use

All original Windows-Use functionality is preserved. The `humphi/` folder
is additive — it does not modify any original files.

See the [original README](https://github.com/CursorTouch/Windows-Use) for
full Windows-Use documentation.

---

Built for [Humphi AI](https://humphi.ai) — Your Personal AI Operating System
