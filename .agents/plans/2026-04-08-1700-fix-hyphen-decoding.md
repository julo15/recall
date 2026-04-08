# Plan: Fix hyphen decoding in `_decode_project_dir`

## Working Protocol
- Small, focused change — single function rewrite + test updates
- Run tests after implementation to verify

## Overview
`_decode_project_dir()` in `recall/adapters/claude.py` naively replaces all `-` with `/`, which corrupts directory names containing literal hyphens (e.g., `qbk-scheduler` → `qbk/scheduler`). Fix by using greedy left-to-right filesystem validation to disambiguate path separators from literal hyphens.

## User Experience
Search results and resume commands currently show wrong project names and broken `cd` paths for any project whose directory name contains a hyphen. After the fix:
- `qbk-scheduler` displays as `qbk-scheduler` (not `qbk/scheduler`)
- Resume commands use the correct `cd /path/to/qbk-scheduler && ...`
- JSON output contains the correct absolute path

## Architecture
**Current flow:** `ClaudeAdapter.load()` reads transcript files from `~/.claude/projects/<encoded-dirname>/`. It calls `_decode_project_dir(encoded_dirname)` to recover the original absolute path, which is stored in `HistoryEntry.project` and used for display (`_format_project`) and resume command construction in `cli.py`.

**Encoding scheme** (done by Claude Code, not by us):
- `/` → `-` (path separator)
- `.` → `-` (dot in hidden dirs like `.cache`, `.claude`)
- Literal `-` in dir names → `-` (unchanged — this is the source of ambiguity)
- This means `--` in encoded names = `/.` (a dot-prefixed directory preceded by a separator)

**What changes:** `_decode_project_dir` gains filesystem awareness. Instead of blind string replacement, it splits on `-`, pre-processes `--` sequences (which encode `.`-prefixed dirs), then greedily walks left-to-right, checking `os.path.isdir()` at each step to decide whether a `-` was a path separator or a literal hyphen. Falls back to the current naive behavior if filesystem validation fails (e.g., deleted project, running in CI).

## Current State
- `_decode_project_dir` at `recall/adapters/claude.py:32-39` — pure string function, no filesystem access
- Tests at `tests/test_claude_adapter.py:49-72` — 3 tests, including one that explicitly documents the lossy behavior as a known limitation
- `_format_project` at `recall/cli.py:21-28` — takes the decoded path and shows last 2 components; no changes needed if decoding is fixed
- Resume command at `recall/cli.py:204-205` — uses raw `project` path for `cd`; also auto-fixed

## Proposed Changes
Rewrite `_decode_project_dir` with a two-phase approach:

1. **Pre-process** `--` sequences: split on `-`, convert empty-token pairs into `.`-prefixed segments (e.g., `['', 'cache']` → `['.cache']`)
2. **Greedy filesystem walk**: starting from `/`, for each token, check if `os.path.join(path, current_segment)` is a directory. If yes, advance the path. If no, append `-token` to the current segment (treating the hyphen as literal).
3. **Fallback**: if the greedy walk fails early (first segment doesn't resolve), fall back to naive `replace("-", "/")` for backwards compatibility and test/CI environments.

This approach is O(n) in the number of path segments, with one `os.path.isdir` call per segment — negligible overhead.

**Why greedy works:** Claude Code generates encoded names from real paths. For a given encoded name, the correct decode is the one where intermediate directories actually exist on disk. The only theoretical failure is if *both* `foo/bar` and `foo-bar` exist as sibling directories — astronomically unlikely and not worth backtracking for.

### Complexity Assessment
**Low.** Single function rewrite (~30 lines), 3 test updates, 0 new files. The function is pure leaf code with no callers except one production site and one test file. No regression risk beyond the function itself.

## Impact Analysis
- **New Files**: None
- **Modified Files**: `recall/adapters/claude.py` (rewrite `_decode_project_dir`), `tests/test_claude_adapter.py` (update tests)
- **Dependencies**: New import of `os.path` in `claude.py` (already imported via `os` on line 3)
- **Similar Modules**: Gemini adapter reads project path from `.project_root` file — no ambiguity there, no changes needed
- **Downstream consumer — seshctl** (`../seshctl`): Consumes recall's `--json` output. The wrong project path currently causes three issues in seshctl, all auto-fixed by this change (no seshctl code changes needed):
  1. Display (`RecallResultRowView.swift:65`): `lastPathComponent` shows `scheduler` instead of `qbk-scheduler`
  2. Resume (`SessionAction.swift:109-116`): `fileExists(atPath:)` check fails on the wrong path, falling through to clipboard fallback with a broken `cd`
  3. Transcript lookup (`TranscriptParser.swift:19-24`): re-encodes the wrong path → can't find the `.jsonl` file

## Implementation Steps

### Step 1: Rewrite `_decode_project_dir` in `recall/adapters/claude.py`
- [x] Add `--` pre-processing: split on `-`, convert empty-token pairs to dot-prefixed segments
- [x] Implement greedy left-to-right filesystem walk using `os.path.isdir`
- [x] Add fallback to naive `replace("-", "/")` when filesystem validation fails (first segment not found)
- [x] Keep handling for non-leading-dash input (relative-style names) unchanged

### Step 2: Update tests in `tests/test_claude_adapter.py`
- [x] Update `test_decode_project_dir_normal` — uses tmp_path fixture for CI portability
- [x] Update `test_decode_project_dir_lossy_hyphenated_segments` — replaced with `test_decode_project_dir_hyphenated_dir` asserting correct behavior
- [x] Add test: hyphenated directory name resolves correctly via filesystem (`test_decode_project_dir_hyphenated_dir`)
- [x] Add test: dot-prefixed directory (`test_decode_project_dir_dot_prefixed`)
- [x] Add test: worktree-style path (`test_decode_project_dir_worktree`)
- [x] Add test: fallback to naive behavior (`test_decode_project_dir_fallback_missing_path`)
- [x] Keep `test_decode_project_dir_no_leading_dash` — relative-style paths still use naive decode

## Acceptance Criteria
- [ ] [test] `recall -S discover` shows `qbk-scheduler` (not `qbk/scheduler`) for sessions in that project
- [ ] [test] Resume command shows correct `cd /Users/.../qbk-scheduler && ...`
- [ ] [test] Paths with dot-prefixed dirs (`.cache`, `.claude/worktrees`) decode correctly
- [ ] [test] Deleted/missing project paths fall back to naive decode without crashing
- [ ] [test] Existing non-hyphenated paths continue to decode correctly

## Edge Cases
- **Project directory deleted**: greedy walk fails at some point → falls back to naive decode. Acceptable — the path was correct when the session was recorded.
- **Both `foo` and `foo-bar` exist as siblings**: greedy picks `foo/bar`. Extremely unlikely in practice. Not worth backtracking.
- **Relative-style encoded name** (no leading dash): keeps current naive behavior.
- **Multiple consecutive hyphens** (`---`): first `--` becomes dot-prefix, remaining `-` is separator or literal. Pre-processing handles this correctly.
