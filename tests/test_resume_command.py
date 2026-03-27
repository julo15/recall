"""Tests for recall.search._resume_command."""

from recall.adapters.base import HistoryEntry
from recall.search import _resume_command


def _make_entry(agent: str = "claude", session_id: str = "abc123", project: str = "") -> HistoryEntry:
    return HistoryEntry(
        text="some text",
        role="user",
        agent=agent,
        session_id=session_id,
        project=project,
        timestamp=1700000000.0,
    )


# -- claude --


def test_claude_resume_command():
    entry = _make_entry(agent="claude", session_id="sess-1")
    assert _resume_command(entry) == "claude --resume sess-1"


def test_claude_skip_permissions():
    entry = _make_entry(agent="claude", session_id="sess-1")
    assert (
        _resume_command(entry, skip_permissions=True)
        == "claude --resume sess-1 --dangerously-skip-permissions"
    )


# -- codex --


def test_codex_resume_command():
    entry = _make_entry(agent="codex", session_id="cx-42")
    assert _resume_command(entry) == "codex --resume cx-42"


# -- gemini --


def test_gemini_resume_command():
    entry = _make_entry(agent="gemini", session_id="gem-99")
    assert _resume_command(entry) == "gemini"


# -- unknown agent --


def test_unknown_agent_returns_empty():
    entry = _make_entry(agent="unknown-agent", session_id="id-1")
    assert _resume_command(entry) == ""


# -- no cd prefix when project is set --


def test_claude_with_project_no_cd_prefix():
    entry = _make_entry(agent="claude", session_id="sess-2", project="/some/project")
    result = _resume_command(entry)
    assert result == "claude --resume sess-2"
    assert "cd " not in result


def test_codex_with_project_no_cd_prefix():
    entry = _make_entry(agent="codex", session_id="cx-7", project="/another/project")
    result = _resume_command(entry)
    assert result == "codex --resume cx-7"
    assert "cd " not in result
