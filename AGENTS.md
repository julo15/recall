# AGENTS.md — recall

Semantic search CLI for AI agent conversation history. Searches across Claude, Codex, and Gemini sessions using local embeddings.

## Prerequisites

- Python 3.10+
- Agent history files from at least one supported agent (Claude, Codex, or Gemini)

## Install

```bash
./install.sh
```

On first search, the index is built automatically (~30s depending on history size). The embedding model (`all-MiniLM-L6-v2`, ~80 MB) is downloaded on first run.

## Usage

```bash
recall "some natural language query"
recall --agent claude "auth bug"
recall --since 2026-03-01 "notification batching"
recall --limit 10 "profile image"
recall --reindex                        # Force full reindex
```

## Architecture

```
recall/
├── cli.py              # Entrypoint (argparse). Entry: recall.cli:main
├── search.py           # Embed query + cosine similarity, dedupe by session
├── index.py            # Build/update index, persist to ~/.recall/
└── adapters/
    ├── base.py         # HistoryEntry dataclass + Adapter protocol
    ├── claude.py       # ~/.claude/projects/*/*.jsonl (transcript JSONL, per-file byte-offset cursors)
    ├── codex.py        # ~/.codex/history.jsonl (JSONL, byte-offset cursor)
    └── gemini.py       # ~/.gemini/tmp/*/logs.json (JSON arrays, seen-set cursor)
```

## Key Design Decisions

- **Local embeddings only** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim). No API keys, works offline.
- **Transcript-level indexing** — indexes user prompts and assistant responses from full conversation transcripts. Provides comprehensive search across all conversation content.
- **Incremental indexing** — each adapter tracks a cursor. Only new entries are embedded on each run.
- **No vector DB** — numpy array + cosine similarity. Sufficient for <100K entries.

## Index Storage

```
~/.recall/
├── embeddings.npy    # (N, 384) float32 numpy array
├── metadata.jsonl    # One HistoryEntry JSON per line, aligned by row
└── cursors.json      # Per-adapter cursor state
```

## Adding a New Agent Adapter

1. Create `recall/adapters/<agent>.py`
2. Implement a class with:
   - `name: str` attribute (agent identifier)
   - `load(cursor: dict | None) -> tuple[list[HistoryEntry], dict]` method
3. Add the class to `ALL_ADAPTERS` in `recall/adapters/__init__.py`
4. Add the agent name to the `--agent` choices in `cli.py`

## Agent History Formats

| Agent | Index File | Format | Prompt Field | Cursor Strategy |
|-------|-----------|--------|-------------|----------------|
| Claude | `~/.claude/projects/*/*.jsonl` | JSONL | `message.content` (user + assistant) | per-file byte offset |
| Codex | `~/.codex/history.jsonl` | JSONL | `text` | byte offset |
| Gemini | `~/.gemini/tmp/*/logs.json` | JSON array | `message` (type=user) | seen (sessionId, messageId) set |

## JSON API Contract

Seshctl and other tools integrate with recall via `recall --json`. This is a stable contract — field names and types must not change without coordinating with consumers.

**Invocation**: `recall --json [-n LIMIT] [--agent AGENT] [--since DATE] "query"`

**Output**: JSON array on stdout. Status messages go to stderr.

**Schema** (each array element):

| Field | Type | Description |
|-------|------|-------------|
| `agent` | string | Source agent: `"claude"`, `"codex"`, or `"gemini"` |
| `role` | string | `"user"` or `"assistant"` |
| `session_id` | string | Session UUID (matches `conversation_id` in seshctl's DB) |
| `project` | string | Project directory path |
| `timestamp` | float | Unix timestamp of the matched entry |
| `score` | float | Cosine similarity score (0.0–1.0) |
| `resume_cmd` | string | Shell command to resume the session (includes `cd` into project dir if known) |
| `text` | string | The matched text content |

**Empty results**: `[]`

**Error**: Non-zero exit code. Stderr may contain error messages.

## Dependencies

- `onnxruntime` + `tokenizers` — embedding model
- `numpy` — vector storage and similarity
- `tqdm` — progress bar during indexing
