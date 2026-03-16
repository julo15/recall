from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from recall.adapters.base import HistoryEntry


@dataclass
class SearchResult:
    entry: HistoryEntry
    score: float
    resume_cmd: str


def _resume_command(entry: HistoryEntry) -> str:
    if entry.agent == "claude":
        return f"claude --resume {entry.session_id}"
    elif entry.agent == "codex":
        return f"codex --resume {entry.session_id}"
    elif entry.agent == "gemini":
        return "gemini"
    return ""


def search(
    query: str,
    embeddings: np.ndarray,
    metadata: list[HistoryEntry],
    limit: int = 5,
    agent_filter: str | None = None,
    since: float | None = None,
) -> list[SearchResult]:
    """Search the index for entries matching the query."""
    from sentence_transformers import SentenceTransformer

    if len(embeddings) == 0 or len(metadata) == 0:
        return []

    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_emb = model.encode([query], normalize_embeddings=False)
    query_vec = np.array(query_emb, dtype=np.float32)[0]

    # Cosine similarity
    norms = np.linalg.norm(embeddings, axis=1)
    query_norm = np.linalg.norm(query_vec)

    # Avoid division by zero
    safe_norms = np.where(norms == 0, 1.0, norms)
    safe_query_norm = query_norm if query_norm > 0 else 1.0

    similarities = embeddings @ query_vec / (safe_norms * safe_query_norm)

    # Build results with filtering
    scored: list[tuple[float, int]] = []
    for i, score in enumerate(similarities):
        entry = metadata[i]

        if agent_filter and entry.agent != agent_filter:
            continue
        if since is not None and entry.timestamp < since:
            continue

        scored.append((float(score), i))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by session_id — keep the best match per session
    seen_sessions: set[tuple[str, str]] = set()
    results: list[SearchResult] = []

    for score, idx in scored:
        entry = metadata[idx]
        session_key = (entry.agent, entry.session_id)

        if session_key in seen_sessions:
            continue
        seen_sessions.add(session_key)

        results.append(
            SearchResult(
                entry=entry,
                score=score,
                resume_cmd=_resume_command(entry),
            )
        )

        if len(results) >= limit:
            break

    return results
