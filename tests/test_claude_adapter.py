"""Tests for recall.adapters.claude parsing helpers."""

from recall.adapters.claude import (
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
