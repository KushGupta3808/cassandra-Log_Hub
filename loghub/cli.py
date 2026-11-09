"""`logq`: search, summarize and tail Cassandra logs from the command line.

Examples:
    logq search --level WARN --since 1h
    logq search --node cassandra-2 --grep "is now DOWN"
    logq stats --since 24h
    logq tail --level ERROR
"""

from __future__ import annotations

import argparse
import sys
import time

from .client import DEFAULT_URL, LogClient, LogHubError
from .query import LEVELS, LogFilter, build_query, build_stats_query

_COLOURS = {"ERROR": "\033[31m", "WARN": "\033[33m", "INFO": "\033[36m", "DEBUG": "\033[90m"}
_RESET = "\033[0m"


def format_entry(source: dict, colour: bool = False) -> str:
    """Render one log document as a single readable line (plus any stack trace)."""
    level = source.get("level", "?")
    tag = f"{_COLOURS.get(level, '')}{level:<5}{_RESET}" if colour else f"{level:<5}"
    location = f"{source.get('source', '?')}:{source.get('line', '?')}"
    message = source.get("message") or source.get("log", "")
    return (f"{source.get('@timestamp', '?')}  {source.get('node', '?'):<11}  {tag}  "
            f"[{source.get('thread', '?')}] {location} - {message}")


def _filter_from_args(args: argparse.Namespace) -> LogFilter:
    return LogFilter(
        min_level=args.level,
        nodes=args.node or [],
        contains=args.grep,
        source=args.source,
        thread=args.thread,
        since=args.since,
        until=getattr(args, "until", None),
    )


def cmd_search(client: LogClient, args: argparse.Namespace) -> int:
    result = client.search(build_query(_filter_from_args(args), size=args.limit))
    hits = result["hits"]["hits"]
    colour = sys.stdout.isatty() and not args.no_colour
    for hit in reversed(hits):  # print oldest first so the output reads top to bottom
        print(format_entry(hit["_source"], colour))
    total = result["hits"].get("total", {}).get("value", len(hits))
    print(f"\n{len(hits)} shown of {total} matching entries", file=sys.stderr)
    return 0


def cmd_stats(client: LogClient, args: argparse.Namespace) -> int:
    aggs = client.search(build_stats_query(_filter_from_args(args))).get("aggregations", {})
    nodes = aggs.get("by_node", {}).get("buckets", [])
    if not nodes:
        print("No matching log entries.")
        return 0
    header = f"{'node':<14}" + "".join(f"{lvl:>8}" for lvl in LEVELS) + f"{'total':>9}"
    print(header)
    print("-" * len(header))
    for bucket in nodes:
        counts = {b["key"]: b["doc_count"] for b in bucket["by_level"]["buckets"]}
        row = "".join(f"{counts.get(lvl, 0):>8}" for lvl in LEVELS)
        print(f"{bucket['key']:<14}{row}{bucket['doc_count']:>9}")
    return 0


def cmd_tail(client: LogClient, args: argparse.Namespace) -> int:
    """Poll for new entries every few seconds, like `tail -f` across all nodes."""
    flt = _filter_from_args(args)
    flt.since = flt.since or "1m"
    colour = sys.stdout.isatty() and not args.no_colour
    seen: set[str] = set()
    try:
        while True:
            hits = client.search(build_query(flt, size=200))["hits"]["hits"]
            for hit in reversed(hits):
                if hit["_id"] not in seen:
                    seen.add(hit["_id"])
                    print(format_entry(hit["_source"], colour), flush=True)
            if len(seen) > 10_000:
                seen = set(list(seen)[-5_000:])
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logq", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help="OpenSearch URL (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_filters(p: argparse.ArgumentParser) -> None:
        p.add_argument("--level", choices=LEVELS, type=str.upper,
                       help="minimum level, e.g. WARN returns WARN and ERROR")
        p.add_argument("--node", action="append", help="limit to a node (repeatable)")
        p.add_argument("--grep", help="phrase the message must contain")
        p.add_argument("--source", help="Java source file, e.g. CompactionTask.java")
        p.add_argument("--thread", help="thread name prefix, e.g. CompactionExecutor")
        p.add_argument("--since", help="start time: duration like 15m/2h/1d or an ISO time")
        p.add_argument("--no-colour", action="store_true", help="disable coloured levels")

    search = sub.add_parser("search", help="find matching log entries")
    add_filters(search)
    search.add_argument("--until", help="end time: duration or ISO time")
    search.add_argument("--limit", type=int, default=50, help="entries to show (default 50)")
    search.set_defaults(func=cmd_search)

    stats = sub.add_parser("stats", help="count entries per node and level")
    add_filters(stats)
    stats.add_argument("--until", help="end time: duration or ISO time")
    stats.set_defaults(func=cmd_stats)

    tail = sub.add_parser("tail", help="follow new entries across all nodes")
    add_filters(tail)
    tail.add_argument("--interval", type=float, default=2.0, help="seconds between polls")
    tail.set_defaults(func=cmd_tail)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(LogClient(args.url), args)
    except (LogHubError, ValueError) as exc:
        print(f"logq: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
