from __future__ import annotations

import argparse
import json
import re
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


def _snippet(text: str, query: str, max_len: int = 120) -> str:
    """Show a snippet centered around the best query word match, or the start if no match."""
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text

    # Find the earliest position of any query word (case-insensitive)
    text_lower = text.lower()
    query_words = [w for w in query.lower().split() if len(w) >= 3]
    best_pos = -1
    for word in query_words:
        pos = text_lower.find(word)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        # No keyword match — show start
        return text[: max_len - 3] + "..."

    # Center the window around the match
    half = max_len // 2
    start = max(0, best_pos - half)
    end = start + max_len

    if end > len(text):
        end = len(text)
        start = max(0, end - max_len)

    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet[3:]
    if end < len(text):
        snippet = snippet[: -3] + "..."
    return snippet


def _highlight(snippet: str, query: str, bold: str, reset: str) -> str:
    """Bold query words found in the snippet."""
    if not bold:
        return snippet
    words = [w for w in query.lower().split() if len(w) >= 3]
    if not words:
        return snippet
    pattern = re.compile("(" + "|".join(re.escape(w) for w in words) + ")", re.IGNORECASE)
    return pattern.sub(f"{bold}\\1{reset}", snippet)


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
    parser.add_argument(
        "--skip-permissions", "-S", action="store_true",
        help="Add --dangerously-skip-permissions to Claude resume commands",
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
        skip_permissions=args.skip_permissions,
    )

    if args.json_output:
        print(json.dumps([
            {
                "agent": r.entry.agent,
                "role": r.entry.role,
                "session_id": r.entry.session_id,
                "project": r.entry.project,
                "timestamp": r.entry.timestamp,
                "score": round(max(0.0, r.score), 4),
                "resume_cmd": r.resume_cmd,
                "text": r.entry.text,
            }
            for r in results
        ]))
        return

    if not results:
        print("No matching sessions found.")
        sys.exit(0)

    use_color = sys.stdout.isatty()
    RESET = "\033[0m" if use_color else ""
    DIM = "\033[2m" if use_color else ""
    CYAN = "\033[36m" if use_color else ""
    YELLOW = "\033[33m" if use_color else ""
    BOLD = "\033[1m" if use_color else ""

    for i, r in enumerate(results, 1):
        project_str = _format_project(r.entry.project)
        date_str = _format_timestamp(r.entry.timestamp)
        snippet = _snippet(r.entry.text, query)
        role_color = YELLOW if r.entry.role == "assistant" else CYAN
        role_label = "bot" if r.entry.role == "assistant" else "you"

        print(f"\n  {i}. [{r.entry.agent}] {date_str}", end="")
        if project_str:
            print(f"  ({project_str})", end="")
        print(f"  score={r.score:.3f}")
        highlighted = _highlight(snippet, query, BOLD, DIM)
        print(f"     {role_color}[{role_label}]{RESET} {DIM}{highlighted}{RESET}")
        if r.entry.project:
            display_cmd = f"cd {r.entry.project} && {r.resume_cmd}"
        else:
            display_cmd = r.resume_cmd
        print(f"     {DIM}> {display_cmd}{RESET}")

    print()


if __name__ == "__main__":
    main()
