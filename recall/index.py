from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

from recall.adapters import ALL_ADAPTERS
from recall.adapters.base import HistoryEntry
from recall.embedding import encode


INDEX_DIR = Path(os.path.expanduser("~/.recall"))
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.npy"
METADATA_PATH = INDEX_DIR / "metadata.jsonl"
CURSORS_PATH = INDEX_DIR / "cursors.json"


def load_cursors() -> dict:
    if CURSORS_PATH.exists():
        try:
            return json.loads(CURSORS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cursors(cursors: dict) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    CURSORS_PATH.write_text(json.dumps(cursors, indent=2) + "\n")


def load_metadata() -> list[HistoryEntry]:
    if not METADATA_PATH.exists():
        return []
    entries = []
    with open(METADATA_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(HistoryEntry.from_json(line))
            except (json.JSONDecodeError, TypeError):
                continue
    return entries


def load_embeddings() -> np.ndarray | None:
    if EMBEDDINGS_PATH.exists():
        return np.load(EMBEDDINGS_PATH)
    return None


def build_index(force: bool = False, json_status: bool = False) -> tuple[np.ndarray, list[HistoryEntry]]:
    """Build or incrementally update the index.

    Returns (embeddings, metadata).
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    cursors = {} if force else load_cursors()
    existing_meta = [] if force else load_metadata()
    existing_emb = None if force else load_embeddings()

    # Collect new entries from all adapters
    all_new: list[HistoryEntry] = []
    new_cursors = dict(cursors)

    for adapter_cls in ALL_ADAPTERS:
        adapter = adapter_cls()
        adapter_cursor = cursors.get(adapter.name)
        entries, new_cursor = adapter.load(adapter_cursor)
        all_new.extend(entries)
        new_cursors[adapter.name] = new_cursor

    if not all_new and existing_emb is not None:
        save_cursors(new_cursors)
        return existing_emb, existing_meta

    # Embed new entries
    if all_new:
        texts = [e.text for e in all_new]
        if json_status:
            print(json.dumps({"status": "indexing", "count": len(texts)}), file=sys.stderr)
        else:
            print(f"Indexing {len(texts)} new entries...", file=sys.stderr)
        new_emb = encode(
            texts,
            show_progress_bar=len(texts) > 50,
            batch_size=64,
        )
    else:
        new_emb = np.empty((0, 384), dtype=np.float32)

    # Merge with existing
    if existing_emb is not None and len(existing_emb) > 0 and len(new_emb) > 0:
        combined_emb = np.vstack([existing_emb, new_emb])
        combined_meta = existing_meta + all_new
    elif existing_emb is not None and len(existing_emb) > 0:
        combined_emb = existing_emb
        combined_meta = existing_meta
    else:
        combined_emb = new_emb
        combined_meta = all_new

    # Persist
    np.save(EMBEDDINGS_PATH, combined_emb)
    with open(METADATA_PATH, "w") as f:
        for entry in combined_meta:
            f.write(entry.to_json() + "\n")
    save_cursors(new_cursors)

    return combined_emb, combined_meta
