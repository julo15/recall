# Plan: Integrate Recall Semantic Search into Seshctl

## Overview
Add recall-powered semantic search to seshctl's `/` search mode. Seshctl will shell out to `recall --json` at runtime, parse the JSON response, and display semantic results below the existing instant substring filter. This plan covers the recall-side prep work (Phase A) and points to the seshctl repo for the integration implementation (Phase B).

## Phase A: Recall repo (completed)

### Step 0: Verify and stabilize recall's JSON contract
- [x] Verify `recall --json` output includes all fields seshctl needs: `agent`, `role`, `session_id`, `project`, `timestamp`, `score`, `resume_cmd`, `text`
- [x] Verify `session_id` in recall output matches `conversation_id` in seshctl's DB (both are Claude's sessionId)
- [x] Add a test in `tests/test_json_output.py` that asserts the JSON schema (field names, types) — this is the contract seshctl depends on
- [x] Document the JSON contract in recall's AGENTS.md under a new "## JSON API Contract" section
- [x] Fix bug: "Indexing N new entries..." was leaking to stdout in --json mode (moved to stderr in index.py)
- [x] PR + merge to main

## Phase B: Seshctl repo

The seshctl-side implementation plan lives in the seshctl repo at `.agents/plans/2026-03-25-1030-recall-search-integration.md`. It covers RecallResult model, RecallService, ViewModel integration, UI changes, and tests.

Recall's JSON API contract is documented in this repo's `AGENTS.md` under "## JSON API Contract".
