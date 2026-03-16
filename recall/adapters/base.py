from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Protocol, runtime_checkable
import json


@dataclass
class HistoryEntry:
    text: str
    agent: str
    session_id: str
    project: str
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> HistoryEntry:
        return cls(**json.loads(line))


@runtime_checkable
class Adapter(Protocol):
    """Protocol for agent history adapters."""

    name: str

    def load(self, cursor: dict | None) -> tuple[list[HistoryEntry], dict]:
        """Load entries since the given cursor.

        Returns (entries, new_cursor).
        """
        ...
