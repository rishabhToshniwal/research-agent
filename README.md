# Research Agents

A Gradio UI for deep research, built with the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/). Enter a question; agents plan searches, query the web in parallel, write a report, and save HTML.

| Component | Role |
|-----------|------|
| **app.py** | Gradio UI — query box, status updates, markdown report |
| **AgentManager** | Orchestrates plan → search → write → print; yields progress |
| **planner_agent** | Turns a query into web search terms (`WebSearchPlan`) |
| **web_search_agent** | Searches via LangSearch and summarizes |
| **writer_agent** | Writes a markdown research report (`ReportData`) |
| **printer_agent** | Converts the report to HTML and saves a `.html` file |

```mermaid
flowchart LR
    ui[Gradio UI] --> manager[AgentManager]
    manager --> planner[planner_agent]
    planner --> gather[asyncio.gather searches]
    gather --> search1[web_search_agent]
    gather --> search2[web_search_agent]
    search1 --> writer[writer_agent]
    search2 --> writer
    writer --> printer[printer_agent]
    printer --> html[Save .html file]
    writer --> ui
```

**Pattern:** orchestration by code — `AgentManager` controls the flow with `Runner.run` and `asyncio.gather`; the UI streams status updates as each step finishes.

```bash
python app.py
```

---

## Prerequisites

- **Python 3.12+**
- **OpenAI API key** — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **LangSearch API key** — for web search

## Setup

```bash
cd research-agents

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Create .env and add keys (see below)
```

## Corporate proxy (optional)

If API calls fail with SSL/certificate errors behind a corporate proxy, [`proxy_patch.py`](proxy_patch.py) disables SSL verification for `httpx` and `requests`. It is imported in `agent_manager.py` / `research.py`:

```python
import proxy_patch
```

- **Behind a corporate proxy:** keep this import.
- **Not behind a proxy:** remove or comment out `import proxy_patch`.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for the agents |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `LANGRAPH_SEARCH_API_KEY` | Yes | LangSearch API key for web search |
| `LANGRAPH_WEB_SEARCH_URL` | No | Override LangSearch endpoint |

## Project layout

```
research-agents/
├── app.py               # Gradio UI entrypoint
├── agent_manager.py     # Orchestration (plan → search → write → print)
├── research.py          # Agents, tools, and structured outputs
├── styles.py            # Gradio CSS, JS, examples, header
├── proxy_patch.py       # Optional: SSL workaround for corporate proxies
├── requirements.txt
├── .env
└── README.md
```

## Traces

Each run creates a trace link (shown in the UI) that opens on the [OpenAI Traces dashboard](https://platform.openai.com/traces).

## License

Use and modify as you like for learning and personal projects.
