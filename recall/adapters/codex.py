from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from recall.adapters.base import Adapter, HistoryEntry


class CodexAdapter:
    name = "codex"

    def __init__(self, history_path: str | None = None):
        self.history_path = Path(
            history_path or os.path.expanduser("~/.codex/history.jsonl")
        )

    def load(self, cursor: dict | None) -> tuple[list[HistoryEntry], dict]:
        if not self.history_path.exists():
            return [], cursor or {}

        offset = (cursor or {}).get("offset", 0)
        file_size = self.history_path.stat().st_size

        if offset >= file_size:
            return [], cursor or {}

        entries: list[HistoryEntry] = []

        with open(self.history_path, "r") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"warning: skipping corrupted line in {self.history_path}",
                        file=sys.stderr,
                    )
                    continue

                text = data.get("text", "")
                if not text or not text.strip():
                    continue

                entries.append(
                    HistoryEntry(
                        text=text,
                        role="user",
                        agent="codex",
                        session_id=data.get("session_id", ""),
                        project="",
                        timestamp=float(data.get("ts", 0)),
                    )
                )

            new_offset = f.tell()

        return entries, {"offset": new_offset}
