from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from recall.index import build_index, load_embeddings, load_metadata, EMBEDDINGS_PATH
from recall.search import search


def _format_timestamp(ts: float) -> str:
    if ts <= 0:
        return "unknown date"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def _format_project(project: str) -> str:
    if not project:
        return ""
    # Show just the last two path components for readability
    parts = project.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return project


def _truncate(text: str, max_len: int = 120) -> str:
    # Collapse whitespace and truncate
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def main():
    parser = argparse.ArgumentParser(
        prog="recall",
        description="Semantic search across AI agent conversation history",
    )
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument(
        "--reindex", action="store_true", help="Force full reindex"
    )
    parser.add_argument(
        "--agent",
        choices=["claude", "codex", "gemini"],
        help="Filter results to a specific agent",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=5, help="Number of results (default: 5)"
    )
    parser.add_argument(
        "--since", type=str, help="Only show results since date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON array",
    )

    args = parser.parse_args()

    # Parse --since
    since_ts: float | None = None
    if args.since:
        try:
            dt = datetime.strptime(args.since, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            since_ts = dt.timestamp()
        except ValueError:
            print(f"error: invalid date format '{args.since}', use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

    # In JSON mode, send status messages to stderr
    log = sys.stderr if args.json_output else sys.stdout

    # Reindex
    if args.reindex:
        print("Rebuilding index from scratch...", file=log)
        build_index(force=True)
        print("Done.", file=log)
        if not args.query:
            return

    query = " ".join(args.query)
    if not query:
        parser.print_help()
        sys.exit(1)

    # Ensure index exists
    if not EMBEDDINGS_PATH.exists():
        print("Building index for the first time...", file=log)
        build_index(force=False)

    embeddings = load_embeddings()
    metadata = load_metadata()

    if embeddings is None or len(metadata) == 0:
        print("No entries indexed. Check that agent history files exist.", file=log)
        if args.json_output:
            print("[]")
        sys.exit(1)

    # Incremental update
    embeddings, metadata = build_index(force=False)

    results = search(
        query=query,
        embeddings=embeddings,
        metadata=metadata,
        limit=args.limit,
        agent_filter=args.agent,
        since=since_ts,
    )

    if args.json_output:
        print(json.dumps([
            {
                "agent": r.entry.agent,
                "session_id": r.entry.session_id,
                "project": r.entry.project,
                "timestamp": r.entry.timestamp,
                "score": round(r.score, 4),
                "resume_cmd": r.resume_cmd,
                "text": r.entry.text,
            }
            for r in results
        ]))
        return

    if not results:
        print("No matching sessions found.")
        sys.exit(0)

    for i, r in enumerate(results, 1):
        project_str = _format_project(r.entry.project)
        date_str = _format_timestamp(r.entry.timestamp)
        snippet = _truncate(r.entry.text)

        print(f"\n  {i}. [{r.entry.agent}] {date_str}", end="")
        if project_str:
            print(f"  ({project_str})", end="")
        print(f"  score={r.score:.3f}")
        print(f"     {snippet}")
        print(f"     > {r.resume_cmd}")

    print()


if __name__ == "__main__":
    main()
