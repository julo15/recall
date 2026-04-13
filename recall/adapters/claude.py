from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from recall.adapters.base import Adapter, HistoryEntry


# Regex to strip internal tags like <system-reminder>...</system-reminder>,
# <local-command-stdout>...</local-command-stdout>, etc.
_STRIP_TAGS = [
    "system-reminder", "local-command-stdout", "local-command-caveat",
    "command-name", "command-message", "command-args",
    "available-deferred-tools", "antml:thinking", "antml:thinking_mode",
    "antml:reasoning_effort",
]
_TAG_RE = re.compile(
    r"<(?:" + "|".join(_STRIP_TAGS) + r")[^>]*>[\s\S]*?</(?:" + "|".join(_STRIP_TAGS) + r")>",
    re.DOTALL,
)


def _strip_tags(text: str) -> str:
    """Remove internal XML tags from text."""
    return _TAG_RE.sub("", text).strip()


def _decode_project_dir(dirname: str) -> str:
    """Naive fallback: convert encoded directory name back to absolute path.

    Claude Code encodes paths by replacing ``/`` and ``.`` with ``-``.
    This is lossy — literal hyphens are indistinguishable from separators.
    Used only as a fallback when transcript entries lack a ``cwd`` field.
    """
    if dirname.startswith("-"):
        return "/" + dirname[1:].replace("-", "/")
    return dirname.replace("-", "/")


def _parse_iso_timestamp(ts: str) -> float:
    """Parse ISO 8601 timestamp to unix float."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0


def _extract_user_text(message: dict) -> str | None:
    """Extract text from a user message, skipping tool results."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    # Array content = tool results, skip
    return None


def _extract_assistant_text(message: dict) -> str | None:
    """Extract text blocks from an assistant message, skipping tool_use/thinking."""
    content = message.get("content", [])
    if not isinstance(content, list):
        return None

    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                texts.append(text)

    return "\n".join(texts) if texts else None


class ClaudeAdapter:
    name = "claude"

    def __init__(self, projects_dir: str | None = None):
        self.projects_dir = Path(
            projects_dir or os.path.expanduser("~/.claude/projects")
        )

    def _find_transcript_files(self) -> list[Path]:
        """Find all transcript JSONL files, excluding subagents."""
        if not self.projects_dir.exists():
            return []

        files = []
        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for f in project_dir.iterdir():
                if f.suffix == ".jsonl" and f.is_file():
                    files.append(f)
        return files

    def load(self, cursor: dict | None) -> tuple[list[HistoryEntry], dict]:
        file_cursors = dict(cursor or {})
        if "offset" in file_cursors:
            print(
                "warning: old index format detected. Run 'recall --reindex' for best results.",
                file=sys.stderr,
            )
            file_cursors = {}
        entries: list[HistoryEntry] = []

        for transcript_path in self._find_transcript_files():
            file_key = str(transcript_path)
            file_cursor = file_cursors.get(file_key, 0)

            # Support both old (bare int) and new (dict) cursor formats
            if isinstance(file_cursor, dict):
                offset = file_cursor.get("offset", 0)
                cached_cwd = file_cursor.get("cwd")
            else:
                offset = file_cursor
                cached_cwd = None

            try:
                file_size = transcript_path.stat().st_size
            except OSError:
                continue

            if offset >= file_size:
                continue

            session_id = transcript_path.stem
            cwd = cached_cwd
            file_entries: list[HistoryEntry] = []

            with open(transcript_path, "r") as f:
                f.seek(offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        print(
                            f"warning: skipping corrupted line in {transcript_path}",
                            file=sys.stderr,
                        )
                        continue

                    # Grab cwd from the first entry that has it
                    if cwd is None and "cwd" in data:
                        cwd = data["cwd"]

                    entry_type = data.get("type")
                    message = data.get("message", {})
                    timestamp = _parse_iso_timestamp(data.get("timestamp", ""))

                    if entry_type == "user":
                        text = _extract_user_text(message)
                        if text:
                            text = _strip_tags(text).strip()
                            if text:
                                file_entries.append(HistoryEntry(
                                    text=text,
                                    role="user",
                                    agent="claude",
                                    session_id=session_id,
                                    project="",  # set after loop from cwd
                                    timestamp=timestamp,
                                ))

                    elif entry_type == "assistant":
                        text = _extract_assistant_text(message)
                        if text:
                            text = _strip_tags(text).strip()
                            if text:
                                file_entries.append(HistoryEntry(
                                    text=text,
                                    role="assistant",
                                    agent="claude",
                                    session_id=session_id,
                                    project="",  # set after loop from cwd
                                    timestamp=timestamp,
                                ))

                new_offset = f.tell()

            # Resolve project: prefer cwd from transcript, fall back to decode
            project = cwd or _decode_project_dir(transcript_path.parent.name)
            for entry in file_entries:
                entry.project = project
            entries.extend(file_entries)

            file_cursors[file_key] = {"offset": new_offset, "cwd": cwd}

        return entries, file_cursors
