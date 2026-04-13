# Plan: Read `cwd` from transcript entries instead of decoding directory names

## Working Protocol
- Small, focused change — modify how `project` is derived in `ClaudeAdapter.load()`
- Run tests after implementation
- Reindex and verify in seshboard (downstream consumer)

## Overview
`_decode_project_dir()` reverse-engineers the project path from Claude Code's encoded directory name (`/` → `-`). This encoding is **lossy** — literal hyphens in directory names are indistinguishable from path separators. Instead of trying to fix the decoder (which has been a whack-a-mole), **stop decoding entirely**. Every transcript entry already has a `cwd` field with the correct, unambiguous absolute path. Just read it.

## User Experience
**Before:** Projects in directories like `ios-3` show as "3" in search results, and resume commands produce `cd .../ios/3` instead of `cd .../ios-3`. This happens whenever a directory prefix also exists on disk (e.g., `ios/` alongside `ios-3/`).

**After:** All project names and paths are correct. The `project` field in JSON output contains the exact path from the transcript.

## Architecture
**Current flow:**
1. `ClaudeAdapter.load()` iterates transcript files in `~/.claude/projects/<encoded-dirname>/`
2. Calls `_decode_project_dir(encoded_dirname)` to recover the absolute path (lossy!)
3. Sets `project = decoded_path` for all `HistoryEntry` objects from that file

**New flow:**
1. Same file iteration
2. For each transcript file, read `cwd` from the first entry that has it
3. Set `project = cwd` — no decoding needed
4. Cache the `cwd` in the file cursor so we have it even when resuming from an offset
5. Fall back to `_decode_project_dir` only for transcripts that somehow lack `cwd` (safety net)

**Why this is better:** `cwd` is the ground truth — written by Claude Code at runtime. `_decode_project_dir` is a lossy heuristic that guesses what the path was. No amount of cleverness (greedy, backtracking, filesystem validation) can fix a fundamentally ambiguous encoding. Reading `cwd` eliminates the entire class of bugs. This is the same approach used by the Gemini adapter, which reads a `.project_root` file instead of decoding.

**Cursor format change:** Currently the cursor stores `{file_path: offset}`. The new format stores `{file_path: {offset: N, cwd: "/path"}}`. Old cursors (plain int offsets) are handled gracefully.

## Current State
- `_decode_project_dir` at `recall/adapters/claude.py:32-83` — greedy filesystem-aware decoder, broken for sibling prefix dirs (e.g., `ios/` exists alongside `ios-3/`)
- `ClaudeAdapter.load()` at line 165 — calls `_decode_project_dir` once per file before parsing entries
- Transcript entries contain `cwd` field on every `user` and `system` entry — already available, just not read
- Tests at `tests/test_claude_adapter.py:49-97` — 7 decode tests

## Proposed Changes
1. **In `ClaudeAdapter.load()`:** Stop calling `_decode_project_dir` as the primary path. Instead, extract `cwd` from the first parsed entry. Store it in the cursor for subsequent reads.
2. **Keep `_decode_project_dir`** as a fallback for edge cases (transcripts without `cwd`, old format files). Don't delete it — just demote it from primary to fallback.
3. **Update cursor format** to store `{offset: int, cwd: str | None}` per file instead of bare int.

### Complexity Assessment
**Low.** ~15 lines changed in the load method, cursor format update, test additions. No new files, no new dependencies. The change makes the code simpler, not more complex.

## Impact Analysis
- **New Files**: None
- **Modified Files**: `recall/adapters/claude.py` (load method), `tests/test_claude_adapter.py` (add cwd-based tests)
- **Dependencies**: None new
- **Similar Modules**: Gemini adapter reads from `.project_root` file — already has the correct path, unaffected
- **Downstream consumers**: seshctl reads the `project` field from recall's JSON output. No seshctl changes needed — correct `project` auto-fixes display, resume, and copy commands.

## Implementation Steps

### Step 1: Update `ClaudeAdapter.load()` in `recall/adapters/claude.py`
- [x] Change cursor format from `{path: offset}` to `{path: {offset: N, cwd: str|None}}`
- [x] Handle migration from old cursor format (bare int → dict)
- [x] While iterating entries, capture `cwd` from the first entry that has it
- [x] Use captured `cwd` as `project` instead of `_decode_project_dir`
- [x] Store `cwd` in cursor for subsequent incremental reads
- [x] Fall back to `_decode_project_dir` only if no `cwd` found in any entry

### Step 2: Write tests
- [x] Add test: `cwd` field in transcript entries is used as project path
- [x] Add test: cursor stores and retrieves `cwd` across incremental loads
- [x] Add test: fallback to `_decode_project_dir` when no `cwd` in entries
- [x] Add test: `cwd` prevents the `ios-3` → `ios/3` misparse
- [x] Verify existing decode tests still pass (they test the fallback path)

### Step 3: Reindex and verify
- [x] Run `recall --reindex` to rebuild with cwd-based paths
- [x] Verify `ios-3` sessions display correctly in seshboard
- [x] Verify copy/resume commands use the correct path

## Acceptance Criteria
- [x] [test] Project path comes from transcript `cwd`, not directory name decoding
- [x] [test] Incremental loads (cursor > 0) still have the correct project path
- [x] [test] Transcripts without `cwd` fall back to decode gracefully
- [x] [test-manual] Seshboard shows `ios-3` not `3`
- [x] [test-manual] Copy command produces `cd .../ios-3 && ...`

## Edge Cases
- **Transcript with no `cwd` entries:** Falls back to `_decode_project_dir`. Unlikely — `cwd` has been in Claude Code transcripts for a long time.
- **Old cursor format (bare int):** Handled gracefully — detected and treated as offset-only with no cached cwd.
- **`cwd` changes mid-transcript:** Use the first `cwd` found — it's the project root. Later `cwd` values in subagents or worktrees would be different, but the first entry is always the project root.
