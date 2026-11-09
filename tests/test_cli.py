import json

import pytest

from loghub import cli
from loghub.client import LogHubError


class FakeClient:
    """Stands in for OpenSearch so the CLI can be tested without a cluster."""

    def __init__(self, response):
        self.response = response
        self.bodies = []

    def search(self, body):
        self.bodies.append(body)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


HIT = {
    "_id": "1",
    "_source": {"@timestamp": "2026-11-09T18:55:40.117Z", "node": "cassandra-2", "level": "WARN",
                "thread": "Native-Transport-Requests-1", "source": "BatchStatement.java",
                "line": 301, "message": "Unlogged batch covering 40 partitions detected"},
}


def run(monkeypatch, argv, response):
    fake = FakeClient(response)
    monkeypatch.setattr(cli, "LogClient", lambda url: fake)
    return cli.main(argv), fake


def test_format_entry_without_colour():
    line = cli.format_entry(HIT["_source"])
    assert "cassandra-2" in line and "WARN" in line
    assert "BatchStatement.java:301 - Unlogged batch" in line


def test_search_prints_entries_and_sends_filters(monkeypatch, capsys):
    response = {"hits": {"hits": [HIT], "total": {"value": 1}}}
    code, fake = run(monkeypatch, ["search", "--level", "warn", "--node", "cassandra-2",
                                   "--since", "1h", "--limit", "5", "--no-colour"], response)
    assert code == 0
    out = capsys.readouterr()
    assert "Unlogged batch covering 40 partitions" in out.out
    assert "1 shown of 1" in out.err
    body = json.dumps(fake.bodies[0])
    assert '"WARN", "ERROR"' in body and "cassandra-2" in body and '"size": 5' in body


def test_stats_prints_a_table(monkeypatch, capsys):
    response = {"hits": {"hits": []}, "aggregations": {"by_node": {"buckets": [
        {"key": "cassandra-1", "doc_count": 7,
         "by_level": {"buckets": [{"key": "INFO", "doc_count": 5}, {"key": "WARN", "doc_count": 2}]}},
    ]}}}
    code, _ = run(monkeypatch, ["stats", "--since", "1d"], response)
    assert code == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["node", "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "total"]
    assert out.splitlines()[2].split() == ["cassandra-1", "0", "0", "5", "2", "0", "7"]


def test_connection_errors_exit_cleanly(monkeypatch, capsys):
    code, _ = run(monkeypatch, ["search"], LogHubError("cannot reach OpenSearch"))
    assert code == 1
    assert "cannot reach OpenSearch" in capsys.readouterr().err


def test_bad_level_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["search", "--level", "FATAL"])
