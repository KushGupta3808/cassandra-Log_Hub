from datetime import datetime, timezone

import pytest

from loghub.query import LogFilter, build_query, build_stats_query, levels_at_or_above

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)


def _filters(body):
    return body["query"]["bool"]["filter"]


def test_empty_filter_matches_everything_newest_first():
    body = build_query(LogFilter(), size=10, now=NOW)
    assert body["size"] == 10
    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert _filters(body) == []
    assert body["sort"][0] == {"@timestamp": "desc"}


def test_min_level_includes_more_severe_levels():
    assert levels_at_or_above("warn") == ["WARN", "ERROR"]
    assert levels_at_or_above("TRACE")[-1] == "ERROR"
    body = build_query(LogFilter(min_level="WARN"), now=NOW)
    assert {"terms": {"level": ["WARN", "ERROR"]}} in _filters(body)


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError):
        levels_at_or_above("FATAL")


def test_nodes_are_deduplicated_and_sorted():
    body = build_query(LogFilter(nodes=["cassandra-3", "cassandra-1", "cassandra-3"]), now=NOW)
    assert {"terms": {"node": ["cassandra-1", "cassandra-3"]}} in _filters(body)


def test_text_source_and_thread_filters():
    body = build_query(LogFilter(contains="is now DOWN", source="Gossiper.java",
                                 thread="GossipStage"), now=NOW)
    assert body["query"]["bool"]["must"] == [{"match_phrase": {"message": "is now DOWN"}}]
    assert {"term": {"source": "Gossiper.java"}} in _filters(body)
    assert {"prefix": {"thread": "GossipStage"}} in _filters(body)


def test_relative_time_range():
    body = build_query(LogFilter(since="2h", until="30m"), now=NOW)
    time_range = [f for f in _filters(body) if "range" in f][0]["range"]["@timestamp"]
    assert time_range == {"gte": "2026-11-09T18:00:00+00:00", "lte": "2026-11-09T19:30:00+00:00"}


def test_search_after_is_passed_through():
    body = build_query(LogFilter(), now=NOW, search_after=["2026-11-09T19:00:00Z", 42])
    assert body["search_after"] == ["2026-11-09T19:00:00Z", 42]


def test_stats_query_aggregates_by_node_and_level_without_hits():
    body = build_stats_query(LogFilter(min_level="WARN", since="1d"), now=NOW)
    assert body["size"] == 0
    assert "sort" not in body
    assert body["aggs"]["by_node"]["terms"]["field"] == "node"
    assert body["aggs"]["by_node"]["aggs"]["by_level"]["terms"]["field"] == "level"
