# Plan: Index Full Transcripts Instead of history.jsonl

## Working Protocol
- Use parallel subagents for independent tasks
- Mark steps done as you complete them
- Run `recall --reindex` and test search after implementation

## Overview
Replace the Claude adapter's history.jsonl-based indexing with full transcript JSONL parsing. This indexes every user prompt and assistant response (not just the last prompt per session), making all conversation content searchable.

## User Experience
1. User runs `recall "Default to profile timeline"` — now finds the session even if that was an early prompt
2. User runs `recall "Claude explained the ONNX model"` — finds sessions by what the assistant said
3. First reindex after upgrade takes ~15-30 seconds (one-time)
4. Incremental updates remain fast (only new transcript lines get indexed)

## Architecture

Recall is a CLI that runs, searches, and exits — no daemon or server. Understanding the two distinct phases is critical:

### Index phase (runs once, then incrementally)
1. Adapters scan source files (history/transcripts) for new entries since last cursor position
2. New text entries are encoded into 384-dim vectors via the ONNX model (~100ms per batch of 64)
3. Vectors are **appended** to `~/.recall/embeddings.npy` (the pre-computed index on disk)
4. Corresponding metadata is appended to `~/.recall/metadata.jsonl`
5. Cursor positions are saved to `~/.recall/cursors.json`

A full reindex re-encodes everything (~15-30s). An incremental update only encodes entries added since the last cursor — typically a handful, taking <1s.

### Query phase (every `recall "query"`)
1. Load `embeddings.npy` from disk into memory (~12-23 MB after this change)
2. Load `metadata.jsonl` from disk (text metadata, ~1-2 MB)
3. Check for new entries via adapters (incremental — usually near-zero work)
4. Encode the single query string into one vector (~100ms)
5. Cosine similarity: compare query vector against all stored vectors (brute-force, <1ms for 8K entries)
6. Return top-N results, exit, memory freed

Key: the query phase **never re-encodes stored text**. It loads pre-computed vectors from disk. The ~30-50 MB memory footprint (model + embeddings + metadata) exists only for the duration of the CLI invocation.

### Storage layout
```
~/.recall/
├── embeddings.npy   # (N, 384) float32 array — all pre-computed vectors
├── metadata.jsonl   # N lines — one HistoryEntry per vector, aligned by row
└── cursors.json     # per-adapter cursor tracking last-indexed position
```

## Current State
- `recall/adapters/claude.py` reads `~/.claude/history.jsonl`, one `display` field per session
- Each session gets exactly one indexed entry (the last prompt)
- 831 entries currently indexed, 1.2 MB embeddings
- Cursor tracks a single byte offset in history.jsonl

### Transcript file structure
- Location: `~/.claude/projects/{encoded-dir}/{sessionId}.jsonl`
- Encoded dir: absolute path with `/` replaced by `-` (e.g., `-Users-julianlo-Documents-me-recall`)
- Each line is a JSON object with a `type` field: `user`, `assistant`, `progress`, `system`, `file-history-snapshot`
- User messages: `message.content` is either a string (real prompt) or an array (tool results — skip these)
- Assistant messages: `message.content` is an array of blocks (`text`, `tool_use`, `thinking` — index `text` blocks only)
- ~95 transcript files, ~16K total entries, ~5-8K after filtering

## Proposed Changes
Replace the Claude adapter to scan transcript files instead of history.jsonl. Use file mtime + byte offset for incremental indexing. Filter to real user prompts and assistant text responses, skipping tool results, tool calls, thinking blocks, progress entries, and system messages.

Each indexable entry maps to one HistoryEntry:
- **User prompt**: `text` = the prompt string, tagged with session_id and project
- **Assistant text**: `text` = the assistant's text response, same session_id and project

The project path is derived from the transcript's parent directory name (reverse the encoding). The session_id is the filename stem.

## Impact Analysis
- **New Files**: None
- **Modified Files**: `recall/adapters/claude.py` (rewrite), `recall/adapters/base.py` (add `role` field to HistoryEntry)
- **Dependencies**: Transcript file format (Claude Code internal, but stable)
- **Index migration**: Requires `--reindex` after upgrade (new data source, incompatible cursors)
- **Size change**: 1.2 MB → ~12-23 MB embeddings, ~831 → ~5-8K entries

## Implementation Steps

### Step 1: Add `role` field to HistoryEntry
- [x] Add `role: str` field to `HistoryEntry` in `recall/adapters/base.py` (values: `"user"` or `"assistant"`)
- [x] Update `to_json` / `from_json` — needs to handle missing `role` for backwards compat during transition

### Step 2: Rewrite Claude adapter
- [x] Replace `recall/adapters/claude.py` to scan `~/.claude/projects/*/` for transcript JSONL files (excluding `subagents/` directories)
- [x] Parse each line: filter to `type: "user"` and `type: "assistant"`
- [x] For user messages: extract `message.content` only when it's a string (skip tool_result arrays)
- [x] For assistant messages: extract `text` blocks from `message.content` array, skip `tool_use`/`thinking`
- [x] Strip internal tags from text (system-reminder, local-command-stdout, etc.)
- [x] Derive project path from directory name, session_id from filename
- [x] Extract timestamp from each entry's `timestamp` field (ISO 8601)
- [x] Cursor system: track per-file `{filename: byte_offset}` so incremental updates only read new lines appended to existing transcripts and new files
- [x] Update codex and gemini adapters to pass `role="user"` to HistoryEntry
- [x] Add `role` field to `--json` output in cli.py

### Step 3: Test
- [x] Run `recall --reindex` — indexed 2300 entries in ~14s
- [x] Search for "Default to profile timeline" — returns semantically related results (exact text was in tool results which are correctly skipped)
- [x] Search for a phrase Claude said (not the user) — assistant text is searchable, role="assistant" appears in results
- [x] Verify `recall --json` — works, includes `role` field

## Acceptance Criteria
- [ ] `recall "Default to profile timeline"` returns the ios-3 session
- [ ] All user prompts across all sessions are searchable
- [ ] Assistant text responses are searchable
- [ ] Tool results and tool calls are not indexed
- [ ] Incremental indexing works (second run only processes new entries)
- [ ] `--json` output includes the `role` field
- [ ] Reindex completes in under 60 seconds

## Edge Cases
- Transcript file is actively being written to (in-progress session): byte offset cursor handles this naturally — reads up to current EOF
- Corrupted JSON line: skip and warn, same as current behavior
- User message with array content (tool results): skip, don't index
- Assistant message with only thinking/tool_use blocks (no text): skip
- Empty text after tag stripping: skip
