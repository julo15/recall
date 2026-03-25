# Plan: Integrate Recall Semantic Search into Seshctl

## Working Protocol
- **Phase A (recall repo)**: Verify recall's JSON contract is complete. PR + merge to main. **Hard stop — do not proceed to Phase B until Phase A is merged.**
- **Phase B (seshctl repo)**: Implement the seshctl integration against recall's stable JSON API.
- Use parallel subagents for independent file reads/edits
- Run `swift test --filter SeshctlCoreTests` and `swift build` after each step
- Mark steps done as you complete them

## Overview
Add recall-powered semantic search to seshctl's `/` search. The existing instant substring filter stays as-is, showing matches in a top "Filter" section. Below it, a "Semantic" section appears (with a loading spinner) showing recall results that arrive ~300ms later via a debounced `Process()` call to `recall --json`.

## User Experience

1. User presses `/` — search mode activates (same as today)
2. User types a query — **instant**: substring filter results appear in a "Filter" section at the top
3. ~300ms after the user stops typing — recall search fires in the background. A spinner appears below the filter results with "Searching..."
4. Recall results arrive — spinner is replaced by a "Semantic" section showing ranked results. Each row shows: project name, date, matched snippet, score, and `[you]`/`[bot]` role tag
5. Results that match sessions in seshctl's DB show full session info (status dot, host app icon, etc.). Results for older/unknown sessions show limited info (project, date, snippet, resume command)
6. User navigates with j/k across both sections
7. User presses Enter on a **filter result** → focuses the session's terminal (existing behavior)
8. User presses Enter on a **semantic result** that's in DB → focuses the session's terminal
9. User presses Enter on a **semantic result** NOT in DB → copies the resume command to clipboard, shows brief "Copied!" feedback
10. If `recall` is not installed, the Semantic section shows an inline message: "Install recall for semantic search: github.com/julo15/recall"

## Architecture

### Current: Substring filter (stays unchanged)
1. User types a character → `appendSearchCharacter()` updates `searchQuery`
2. `filteredSessions` (computed property) runs synchronous substring match against all sessions in memory
3. View re-renders instantly with filtered results
4. All data is already in memory from the 2-second polling cycle

### New: Recall search (runs in parallel)
1. User types a character → `appendSearchCharacter()` updates `searchQuery` AND resets a debounce timer (300ms)
2. When the debounce timer fires:
   - Set `isRecallSearching = true` (shows spinner in UI)
   - Spawn a `Task.detached` that runs `Process()` calling `recall --json -n 10 "<query>"`
   - Parse the JSON response into `[RecallResult]`
3. When the task completes:
   - Set `recallResults = parsed results` and `isRecallSearching = false`
   - Match each result's `session_id` against seshctl's DB to determine if we can focus the session or need to copy the resume command
4. If the user types more before recall returns:
   - Cancel the in-flight task
   - Restart the debounce timer
   - Filter results clear immediately; recall results stay until new ones arrive (avoids flicker)

### Process invocation
- Use `/usr/bin/env recall` (follows PATH, works with ~/.local/bin install)
- stdout → JSON array, stderr → /dev/null
- Run on a detached task to avoid blocking main thread
- Timeout after 5 seconds (kill the process if recall hangs)
- If `recall` not found (terminationStatus != 0 or file-not-found), set a `recallUnavailable` flag

### Memory/performance
- No persistent state between searches — each search spawns a fresh `recall` process
- Recall loads its model + embeddings on each invocation (~30-50MB, ~200ms). This is recall's architecture, not something seshctl controls
- Seshctl itself adds minimal overhead: one `Process` + JSON decode per debounce cycle

## Current State

### Seshctl search (`SessionListViewModel.swift`)
- `isSearching: Bool`, `searchQuery: String`, `isNavigatingSearch: Bool`
- `filteredSessions` computed property: substring match on directory, gitRepoName, gitBranch, lastAsk, lastReply, tool
- `orderedSessions` splits into `activeSessions` + `recentSessions` for rendering
- No async search, no external process calls from the ViewModel

### Seshctl Process patterns
- `GitContext.swift`: Sync `Process()` with `waitUntilExit()`, stdout pipe, check terminationStatus
- `WindowFocuser.swift`: Same pattern for `ps`, `osascript`, `open`
- No existing async Process patterns — will need to introduce one

### Recall JSON output
- `recall --json -n 10 "query"` outputs a JSON array to stdout
- Each element: `{agent, role, session_id, project, timestamp, score, resume_cmd, text}`
- Status messages go to stderr
- Empty results: `[]`

## Proposed Changes

### Component 1: RecallService (new, in SeshctlCore)
A lightweight Swift service that shells out to `recall --json` and decodes the response. Async interface, cancellable, with timeout. Follows the same `Process()` pattern as GitContext but wrapped in Swift concurrency.

### Component 2: RecallResult model (new, in SeshctlCore)
A `Codable` struct matching recall's JSON output. Plus a computed `matchedSession: Session?` property that gets populated by cross-referencing with seshctl's DB.

### Component 3: SessionListViewModel updates (modified)
- Add `recallResults: [RecallResult]`, `isRecallSearching: Bool`, `recallUnavailable: Bool`
- Add debounce logic: on each search character, cancel pending recall task, start new 300ms timer
- Add `selectedSection` tracking so j/k navigation works across both sections
- Add action handling: Enter on recall result either focuses session or copies resume command

### Component 4: SessionListView updates (modified)
- Below the existing session list (filter results), add a "Semantic" section
- Show spinner when `isRecallSearching`
- Show `RecallResultRow` for each result (project, date, snippet, score, role tag)
- Show "Install recall" message when `recallUnavailable`
- Dim recall results that don't have a matching DB session (to signal limited functionality)

### Complexity Assessment
**Medium.** 4-5 new/modified files. The Process + async pattern is new to the ViewModel but follows existing repo patterns. The main complexity is the two-section navigation (j/k across filter + semantic results) and debounce cancellation. No new dependencies, no database changes.

## Impact Analysis
- **New Files (in seshctl repo)**:
  - `Sources/SeshctlCore/RecallService.swift` — Process wrapper, JSON decode
  - `Sources/SeshctlCore/RecallResult.swift` — Data model
  - `Sources/SeshctlUI/RecallResultRowView.swift` — Row view for semantic results
- **Modified Files (in seshctl repo)**:
  - `Sources/SeshctlUI/SessionListViewModel.swift` — Debounce, recall state, two-section nav
  - `Sources/SeshctlUI/SessionListView.swift` — Semantic section rendering
- **Dependencies**: `recall` CLI must be on PATH (`~/.local/bin/recall`)
- **Similar Modules**: `GitContext.swift` (Process pattern), `TranscriptParser.swift` (JSON parsing)

## Key Decisions
- **Hybrid search**: Filter results on top (instant), semantic results below (debounced). User requested this explicitly.
- **Debounce, not Enter**: Recall fires 300ms after last keystroke, not on explicit Enter. Feels more responsive.
- **Focus-or-copy**: Enter on a semantic result focuses the session if in DB, otherwise copies resume command to clipboard.
- **No recall dependency at build time**: Seshctl doesn't import recall. It's a runtime dependency discovered via PATH.
- **Graceful degradation**: If recall isn't installed, show a helpful message in the semantic section. Filter search works normally.

## Implementation Steps

### Phase A: Recall repo (PR + merge first)

### Step 0: Verify and stabilize recall's JSON contract
- [x] Verify `recall --json` output includes all fields seshctl needs: `agent`, `role`, `session_id`, `project`, `timestamp`, `score`, `resume_cmd`, `text`
- [x] Verify `session_id` in recall output matches `conversation_id` in seshctl's DB (both are Claude's sessionId)
- [x] Add a test in `tests/test_json_output.py` that asserts the JSON schema (field names, types) — this is the contract seshctl depends on
- [x] Document the JSON contract in recall's AGENTS.md under a new "## JSON API Contract" section
- [x] Fix bug: "Indexing N new entries..." was leaking to stdout in --json mode (moved to stderr in index.py)
- [ ] **PR + merge to main. Hard stop here.**

### Phase B: Seshctl repo (after Phase A is merged)

### Step 1: RecallResult model
- [ ] Create `Sources/SeshctlCore/RecallResult.swift` — Codable struct with fields: agent, role, sessionId, project, timestamp, score, resumeCmd, text
- [ ] Add CodingKeys for snake_case JSON mapping (session_id → sessionId, resume_cmd → resumeCmd)

### Step 2: RecallService
- [ ] Create `Sources/SeshctlCore/RecallService.swift`
- [ ] Implement `static func search(query: String, limit: Int = 10) async throws -> [RecallResult]`
- [ ] Use `Process()` with `/usr/bin/env recall --json -n <limit> <query>`
- [ ] Parse stdout JSON into `[RecallResult]`
- [ ] Handle errors: recall not found (throw specific error), timeout (5s), bad JSON
- [ ] Implement `static func isAvailable() -> Bool` — check if `recall` is on PATH

### Step 3: ViewModel integration
- [ ] Add to `SessionListViewModel`: `recallResults`, `isRecallSearching`, `recallUnavailable`, `recallSearchTask`
- [ ] In `appendSearchCharacter()` and `deleteSearchCharacter()`: cancel existing recall task, start new debounced task (300ms delay)
- [ ] In the debounced task: call `RecallService.search()`, update `recallResults` on main actor
- [ ] In `exitSearch()`: cancel recall task, clear recallResults
- [ ] Add two-section navigation: `orderedSessions` + `recallResults` as a unified selectable list. Track which section the selection is in.
- [ ] Add Enter handler for recall results: if session_id matches a DB session, focus it. Otherwise, copy resumeCmd to pasteboard.

### Step 4: UI — Semantic section
- [ ] In `SessionListView.swift`: below the existing session list sections, add a "Semantic" section (only visible when `isSearching`)
- [ ] Show a spinner row when `isRecallSearching`
- [ ] Show `RecallResultRowView` for each recall result
- [ ] Show "Install recall for semantic search" when `recallUnavailable`
- [ ] Create `Sources/SeshctlUI/RecallResultRowView.swift` — display project (last 2 components), relative date, matched snippet (truncated), score, role tag ([you]/[bot])
- [ ] Dim rows for results without a matching DB session

### Step 5: Write Tests
- [ ] Create `Tests/SeshctlCoreTests/RecallResultTests.swift`
  - [ ] Test JSON decoding from real recall output (snake_case mapping)
  - [ ] Test decoding empty array `[]`
  - [ ] Test decoding with missing optional fields
- [ ] Create `Tests/SeshctlCoreTests/RecallServiceTests.swift`
  - [ ] Test `isAvailable()` returns false when recall not on PATH
  - [ ] Test search with a mock/stub approach (or integration test if recall is installed)
- [ ] Update `Tests/SeshctlUITests/SessionListViewModelTests.swift` (if exists)
  - [ ] Test that search triggers debounced recall search
  - [ ] Test that rapid typing cancels previous recall task
  - [ ] Test that exitSearch clears recall results

## Acceptance Criteria
- [ ] [test] RecallResult JSON decoding handles real recall output correctly
- [ ] [test] RecallResult decoding handles empty arrays and edge cases
- [ ] [test-manual] Typing in `/` search shows instant filter results on top
- [ ] [test-manual] ~300ms after typing stops, semantic results appear below with a brief spinner
- [ ] [test-manual] Rapid typing cancels previous recall searches (no stale results)
- [ ] [test-manual] Enter on a semantic result that's in DB focuses the terminal
- [ ] [test-manual] Enter on a semantic result NOT in DB copies resume command and shows feedback
- [ ] [test-manual] When recall is not installed, semantic section shows install message
- [ ] [test-manual] j/k navigation works across both filter and semantic sections seamlessly

## Edge Cases
- **Recall not installed**: Show inline install message in semantic section. Filter search unaffected.
- **Recall returns empty `[]`**: Hide semantic section (don't show empty header)
- **Recall times out (>5s)**: Cancel process, show "Search timed out" briefly, allow retry on next keystroke
- **User exits search while recall is running**: Cancel the in-flight task immediately
- **Very long query**: Recall handles truncation internally (tokenizer truncates at 256 tokens)
- **No index yet (first run)**: Recall will auto-build the index, but this takes ~15-30s. Show spinner with "Building search index..." if recall takes >2s. Subsequent searches are fast.
- **Duplicate results**: A session might appear in both filter results and semantic results. Deduplicate by session_id — if it's already in filter results, exclude from semantic results.
