"""Tests for recall.adapters.claude parsing helpers."""

import json

from recall.adapters.claude import (
    ClaudeAdapter,
    _decode_project_dir,
    _extract_assistant_text,
    _extract_user_text,
    _parse_iso_timestamp,
    _strip_tags,
)


# -- _strip_tags --


def test_strip_tags_removes_system_reminder():
    text = "Hello <system-reminder>secret stuff</system-reminder> world"
    assert _strip_tags(text) == "Hello  world"


def test_strip_tags_removes_local_command_stdout():
    text = "before <local-command-stdout>output</local-command-stdout> after"
    assert _strip_tags(text) == "before  after"


def test_strip_tags_removes_nested_content():
    text = '<system-reminder attr="1"><inner>deep</inner></system-reminder>kept'
    assert _strip_tags(text) == "kept"


def test_strip_tags_no_tags():
    text = "plain text with no tags"
    assert _strip_tags(text) == "plain text with no tags"


def test_strip_tags_only_tags():
    text = "<system-reminder>everything</system-reminder>"
    assert _strip_tags(text) == ""


def test_strip_tags_multiple_different_tags():
    text = (
        "<system-reminder>a</system-reminder>"
        "keep"
        "<available-deferred-tools>b</available-deferred-tools>"
    )
    assert _strip_tags(text) == "keep"


# -- _decode_project_dir --


def test_decode_project_dir_normal(tmp_path):
    # Build a real directory tree so the greedy walk can resolve it
    (tmp_path / "Users" / "julianlo" / "Documents" / "me" / "recall").mkdir(parents=True)
    encoded = f"-{str(tmp_path)[1:]}-Users-julianlo-Documents-me-recall"
    assert _decode_project_dir(encoded) == str(tmp_path / "Users" / "julianlo" / "Documents" / "me" / "recall")


def test_decode_project_dir_no_leading_dash():
    # Relative-style encoded name (no leading dash) — naive fallback
    assert _decode_project_dir("some-project") == "some/project"


def test_decode_project_dir_hyphenated_dir(tmp_path):
    # Directory with a literal hyphen should be preserved
    (tmp_path / "Users" / "julianlo" / "Documents" / "me" / "qbk-scheduler").mkdir(parents=True)
    encoded = f"-{str(tmp_path)[1:]}-Users-julianlo-Documents-me-qbk-scheduler"
    assert _decode_project_dir(encoded) == str(tmp_path / "Users" / "julianlo" / "Documents" / "me" / "qbk-scheduler")


def test_decode_project_dir_dot_prefixed(tmp_path):
    # Double-hyphen encodes a dot-prefixed directory (e.g. .cache)
    (tmp_path / "Users" / "julianlo" / ".cache" / "pr-watch-repos").mkdir(parents=True)
    encoded = f"-{str(tmp_path)[1:]}-Users-julianlo--cache-pr-watch-repos"
    assert _decode_project_dir(encoded) == str(tmp_path / "Users" / "julianlo" / ".cache" / "pr-watch-repos")


def test_decode_project_dir_worktree(tmp_path):
    # Worktree path: hyphens in dir name + dot-prefixed .claude/worktrees + hyphens in worktree name
    (tmp_path / "Users" / "julianlo" / "Documents" / "me" / "qbk-scheduler" / ".claude" / "worktrees" / "julo-pull-to-refresh").mkdir(parents=True)
    encoded = f"-{str(tmp_path)[1:]}-Users-julianlo-Documents-me-qbk-scheduler--claude-worktrees-julo-pull-to-refresh"
    assert _decode_project_dir(encoded) == str(tmp_path / "Users" / "julianlo" / "Documents" / "me" / "qbk-scheduler" / ".claude" / "worktrees" / "julo-pull-to-refresh")


def test_decode_project_dir_fallback_missing_path():
    # When the path doesn't exist on disk, fall back to naive decode
    encoded = "-NoSuchRoot-fake-dir-my-project"
    assert _decode_project_dir(encoded) == "/NoSuchRoot/fake/dir/my/project"


def test_decode_project_dir_leaf_not_on_disk(tmp_path):
    # Parent exists but the project dir itself does not — leaf accumulates correctly
    (tmp_path / "Users" / "julianlo" / "Documents" / "me").mkdir(parents=True)
    encoded = f"-{str(tmp_path)[1:]}-Users-julianlo-Documents-me-qbk-scheduler"
    assert _decode_project_dir(encoded) == str(
        tmp_path / "Users" / "julianlo" / "Documents" / "me" / "qbk-scheduler"
    )


# -- _extract_user_text --


def test_extract_user_text_string_content():
    msg = {"content": "hello world"}
    assert _extract_user_text(msg) == "hello world"


def test_extract_user_text_array_content_returns_none():
    msg = {"content": [{"type": "tool_result", "content": "data"}]}
    assert _extract_user_text(msg) is None


def test_extract_user_text_empty_content():
    msg = {"content": ""}
    assert _extract_user_text(msg) == ""


def test_extract_user_text_missing_content():
    msg = {}
    assert _extract_user_text(msg) == ""


# -- _extract_assistant_text --


def test_extract_assistant_text_text_blocks():
    msg = {"content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]}
    assert _extract_assistant_text(msg) == "hello\nworld"


def test_extract_assistant_text_skips_tool_use():
    msg = {
        "content": [
            {"type": "tool_use", "id": "1", "name": "bash", "input": {}},
            {"type": "text", "text": "result"},
        ]
    }
    assert _extract_assistant_text(msg) == "result"


def test_extract_assistant_text_skips_thinking():
    msg = {
        "content": [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "answer"},
        ]
    }
    assert _extract_assistant_text(msg) == "answer"


def test_extract_assistant_text_no_text_blocks():
    msg = {"content": [{"type": "tool_use", "id": "1", "name": "bash", "input": {}}]}
    assert _extract_assistant_text(msg) is None


def test_extract_assistant_text_non_list_content():
    msg = {"content": "just a string"}
    assert _extract_assistant_text(msg) is None


def test_extract_assistant_text_empty_list():
    msg = {"content": []}
    assert _extract_assistant_text(msg) is None


# -- _parse_iso_timestamp --


def test_parse_iso_timestamp_valid():
    ts = "2026-03-19T16:00:00+00:00"
    result = _parse_iso_timestamp(ts)
    assert result > 0


def test_parse_iso_timestamp_z_suffix():
    ts = "2026-03-19T16:00:00Z"
    result = _parse_iso_timestamp(ts)
    assert result > 0
    # Should equal the explicit +00:00 variant
    assert result == _parse_iso_timestamp("2026-03-19T16:00:00+00:00")


def test_parse_iso_timestamp_invalid():
    assert _parse_iso_timestamp("not-a-date") == 0.0


def test_parse_iso_timestamp_empty():
    assert _parse_iso_timestamp("") == 0.0


# -- ClaudeAdapter.load() — cwd extraction --


def _write_transcript(projects_dir, encoded_dirname, session_id, entries):
    """Helper to write a transcript JSONL file."""
    project_dir = projects_dir / encoded_dirname
    project_dir.mkdir(parents=True, exist_ok=True)
    transcript = project_dir / f"{session_id}.jsonl"
    with open(transcript, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return transcript


def test_load_uses_cwd_from_transcript(tmp_path):
    """Project path should come from cwd field in transcript, not dirname decode."""
    _write_transcript(tmp_path, "-Users-me-ios-3", "sess1", [
        {"type": "user", "cwd": "/Users/me/ios-3", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": "hello"}},
    ])
    adapter = ClaudeAdapter(projects_dir=str(tmp_path))
    entries, _ = adapter.load(None)
    assert len(entries) == 1
    assert entries[0].project == "/Users/me/ios-3"


def test_load_cwd_cached_in_cursor(tmp_path):
    """Once cwd is found, it should be cached in the cursor for incremental loads."""
    _write_transcript(tmp_path, "-Users-me-ios-3", "sess1", [
        {"type": "user", "cwd": "/Users/me/ios-3", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": "hello"}},
    ])
    adapter = ClaudeAdapter(projects_dir=str(tmp_path))
    _, cursor = adapter.load(None)

    file_key = str(tmp_path / "-Users-me-ios-3" / "sess1.jsonl")
    assert cursor[file_key]["cwd"] == "/Users/me/ios-3"


def test_load_uses_cached_cwd_on_incremental_load(tmp_path):
    """Incremental load should use cwd from cursor even if new entries lack cwd."""
    transcript = _write_transcript(tmp_path, "-Users-me-ios-3", "sess1", [
        {"type": "user", "cwd": "/Users/me/ios-3", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": "first"}},
    ])
    adapter = ClaudeAdapter(projects_dir=str(tmp_path))
    _, cursor = adapter.load(None)

    # Append a new entry without cwd
    with open(transcript, "a") as f:
        f.write(json.dumps({
            "type": "user", "timestamp": "2026-01-02T00:00:00Z",
            "message": {"content": "second"},
        }) + "\n")

    entries, cursor2 = adapter.load(cursor)
    assert len(entries) == 1
    assert entries[0].project == "/Users/me/ios-3"
    assert entries[0].text == "second"


def test_load_falls_back_to_decode_without_cwd(tmp_path):
    """When no entry has cwd, should fall back to _decode_project_dir."""
    # Use a simple encoded name that doesn't contain real path separators
    _write_transcript(tmp_path, "-NoSuchRoot-my-project", "sess1", [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": "hello"}},
    ])
    adapter = ClaudeAdapter(projects_dir=str(tmp_path))
    entries, _ = adapter.load(None)
    assert len(entries) == 1
    # Falls back to naive decode since /NoSuchRoot doesn't exist
    assert entries[0].project == "/NoSuchRoot/my/project"


def test_load_cwd_prevents_hyphen_misparse(tmp_path):
    """The original bug: ios-3 was decoded as ios/3. With cwd, it's correct."""
    _write_transcript(tmp_path, "-Users-me-mozi-ios-3", "sess1", [
        {"type": "user", "cwd": "/Users/me/mozi/ios-3", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": "fix the build"}},
    ])
    adapter = ClaudeAdapter(projects_dir=str(tmp_path))
    entries, _ = adapter.load(None)
    assert len(entries) == 1
    assert entries[0].project == "/Users/me/mozi/ios-3"
    # Would have been /Users/me/mozi/ios/3 with the old decode
