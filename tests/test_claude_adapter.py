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


def test_decode_project_dir_normal():
    assert (
        _decode_project_dir("-Users-julianlo-Documents-me-recall")
        == "/Users/julianlo/Documents/me/recall"
    )


def test_decode_project_dir_no_leading_dash():
    # Relative-style encoded name (no leading dash)
    assert _decode_project_dir("some-project") == "some/project"


def test_decode_project_dir_lossy_hyphenated_segments():
    # Known limitation: real hyphens in directory names are indistinguishable
    # from separators, so 'my-project' in the path becomes 'my/project'.
    encoded = "-Users-julianlo-my-project"
    result = _decode_project_dir(encoded)
    # The function cannot recover the original hyphen — this documents the
    # lossy behaviour rather than asserting correctness.
    assert result == "/Users/julianlo/my/project"
    assert result != "/Users/julianlo/my-project"  # the real path is lost


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
