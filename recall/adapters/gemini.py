from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from recall.adapters.base import Adapter, HistoryEntry


class GeminiAdapter:
    name = "gemini"

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(
            base_dir or os.path.expanduser("~/.gemini/tmp")
        )

    def load(self, cursor: dict | None) -> tuple[list[HistoryEntry], dict]:
        if not self.base_dir.exists():
            return [], cursor or {}

        seen = set(tuple(x) for x in (cursor or {}).get("seen", []))
        entries: list[HistoryEntry] = []
        new_seen = set(seen)

        for logs_file in self.base_dir.glob("*/logs.json"):
            try:
                with open(logs_file, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                print(
                    f"warning: skipping corrupted file {logs_file}",
                    file=sys.stderr,
                )
                continue

            if not isinstance(data, list):
                continue

            # Read project root from sibling .project_root file
            project_root_file = logs_file.parent / ".project_root"
            project = ""
            if project_root_file.exists():
                try:
                    project = project_root_file.read_text().strip()
                except OSError:
                    pass

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") != "user":
                    continue

                session_id = msg.get("sessionId", "")
                message_id = msg.get("messageId", 0)
                key = (session_id, str(message_id))

                if key in seen:
                    continue

                text = msg.get("message", "")
                if not text or not text.strip():
                    new_seen.add(key)
                    continue

                # Parse ISO 8601 timestamp
                ts_str = msg.get("timestamp", "")
                timestamp = 0.0
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamp = dt.timestamp()
                    except (ValueError, OSError):
                        pass

                entries.append(
                    HistoryEntry(
                        text=text,
                        agent="gemini",
                        session_id=session_id,
                        project=project,
                        timestamp=timestamp,
                    )
                )
                new_seen.add(key)

        new_cursor = {"seen": [list(x) for x in new_seen]}
        return entries, new_cursor
