"""Build OpenSearch query DSL from simple log filters.

Kept free of network calls so every filter combination can be unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .timeparse import to_timestamp

LEVELS = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]


@dataclass
class LogFilter:
    """Filters a user can combine when searching Cassandra logs."""

    min_level: str | None = None          # e.g. "WARN" returns WARN and ERROR
    nodes: list[str] = field(default_factory=list)
    contains: str | None = None           # full-text match on the message
    source: str | None = None             # Java source file, e.g. "CompactionTask.java"
    thread: str | None = None             # thread name prefix, e.g. "CompactionExecutor"
    since: str | None = None              # "15m", "2h" or an ISO time
    until: str | None = None


def levels_at_or_above(level: str) -> list[str]:
    """Return the given level and every more severe one."""
    level = level.upper()
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; choose from {', '.join(LEVELS)}")
    return LEVELS[LEVELS.index(level):]


def build_query(flt: LogFilter, size: int = 50, now: datetime | None = None,
                search_after: list | None = None) -> dict:
    """Translate a LogFilter into an OpenSearch search body, newest entries first."""
    must: list[dict] = []
    filters: list[dict] = []

    if flt.min_level:
        filters.append({"terms": {"level": levels_at_or_above(flt.min_level)}})
    if flt.nodes:
        filters.append({"terms": {"node": sorted(set(flt.nodes))}})
    if flt.source:
        filters.append({"term": {"source": flt.source}})
    if flt.thread:
        filters.append({"prefix": {"thread": flt.thread}})
    if flt.contains:
        must.append({"match_phrase": {"message": flt.contains}})

    time_range: dict[str, str] = {}
    if flt.since:
        time_range["gte"] = to_timestamp(flt.since, now)
    if flt.until:
        time_range["lte"] = to_timestamp(flt.until, now)
    if time_range:
        filters.append({"range": {"@timestamp": time_range}})

    body: dict = {
        "size": size,
        "sort": [{"@timestamp": "desc"}, {"_doc": "desc"}],
        "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
    }
    if search_after:
        body["search_after"] = search_after
    return body


def build_stats_query(flt: LogFilter, now: datetime | None = None) -> dict:
    """Count matching entries per node and per level, without returning documents."""
    body = build_query(flt, size=0, now=now)
    body.pop("sort")
    body["aggs"] = {
        "by_node": {
            "terms": {"field": "node", "size": 20},
            "aggs": {"by_level": {"terms": {"field": "level", "size": len(LEVELS)}}},
        },
        "by_level": {"terms": {"field": "level", "size": len(LEVELS)}},
    }
    return body
