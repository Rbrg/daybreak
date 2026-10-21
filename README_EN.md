# daybreak

A command-line LLM agent built from scratch on the **Claude Messages API** —
no LangChain, no agent frameworks. A single `anthropic` SDK dependency,
everything else is the Python standard library.

Built as a learning project and a reference implementation of the moving
parts of an LLM agent: the tool-call loop, streaming, RAG, multi-agent
orchestration, and evaluation.

## Features

- **Streaming REPL** — thinking streams dimmed, text streams token by token,
  tool calls visible as they happen
- **Hand-written agentic loop** — full control over `stop_reason` dispatch
  (`tool_use` / `pause_turn` / `max_tokens`), thinking blocks preserved
  across turns
- **6 built-in tools** — current time, safe calculator (AST whitelist),
  sandboxed file reader, knowledge-base search, document listing,
  sub-agent delegation
- **RAG pipeline** — drop `.md`/`.txt`/`.pdf` files into `knowledge/`;
  paragraph chunking with overlap, jieba Chinese tokenization, BM25
  retrieval with source citations. The retrieval layer is abstracted so
  vector search can replace it without touching the tool layer
- **Multi-agent orchestration** — the main agent can delegate subtasks to
  role-based sub-agents (researcher / coder); a depth cap prevents
  recursive spawning
- **Evaluation** — `python -m evals` runs a test set and reports tool
  selection accuracy and keyword hit rates
- **Engineering** — 45 unit tests (pytest), ruff lint, GitHub Actions CI,
  Docker image

## Quick Start

Requires Python 3.10+ and an Anthropic API key (or any Anthropic-compatible
gateway).

```bash
pip install anthropic jieba pypdf

# Configure credentials (recommended: .env file, loaded automatically)
cp .env.example .env   # then edit .env

# Run
python -m daybreak
```

### Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Official Claude API key | — |
| `ANTHROPIC_AUTH_TOKEN` | Gateway token (with `ANTHROPIC_BASE_URL`) | — |
| `AGENT_MODEL` | Model ID | `claude-opus-5-5` |
| `AGENT_WORKSPACE` | Sandbox root for `read_file` | current directory |
| `AGENT_KNOWLEDGE_DIR` | RAG knowledge directory | `./knowledge/` |

### Commands

`/help` `/tools` `/kb` `/reindex` `/reset` `/quit` (or Ctrl+C / Ctrl+D)

## Architecture

```
daybreak/
├── core.py        # Agent class: hand-written agentic loop + streaming
├── cli.py         # REPL, stream rendering, error handling
├── tools.py       # @beta_tool tool definitions + registry
├── subagents.py   # role-based sub-agent spawning
└── rag/           # RAG subsystem
    ├── loader.py    # document loading (.md/.txt/.pdf)
    ├── chunker.py   # paragraph chunking + overlap window
    ├── index.py     # BM25 retrieval (swappable for vector search)
    └── __init__.py  # KnowledgeBase facade
```

## Adding Your Own Tool

Write a function with type annotations and a docstring, decorate it with
`@beta_tool`, and register it in `BASE_TOOLS` in `daybreak/tools.py`:

```python
@beta_tool
def get_weather(location: str) -> str:
    """Get the weather for a city.

    Args:
        location: City name, e.g. "Beijing".
    """
    return f"{location}: sunny, 25C"

BASE_TOOLS = [get_current_time, calculator, read_file, get_weather, ...]
```

The JSON schema is generated from the signature and docstring — the `Args`
section is what the model reads to decide when and how to call the tool.

## Development

```bash
pip install pytest ruff
pytest -v          # 45 unit tests, all offline
ruff check .       # lint
python -m evals    # evaluation suite (needs API credentials)
```

Docker:

```bash
docker build -t daybreak .
docker run -it --env-file .env daybreak
```

## License

[MIT](LICENSE)
