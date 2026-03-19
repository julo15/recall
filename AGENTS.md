# AGENTS.md — recall

Semantic search CLI for AI agent conversation history. Searches across Claude, Codex, and Gemini sessions using local embeddings.

## Prerequisites

- Python 3.10+
- Agent history files from at least one supported agent (Claude, Codex, or Gemini)

## Install

```bash
pip install -e .
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

## Dependencies

- `onnxruntime` + `tokenizers` — embedding model
- `numpy` — vector storage and similarity
- `tqdm` — progress bar during indexing
