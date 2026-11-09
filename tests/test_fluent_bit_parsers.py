"""Check the regexes in fluent-bit/parsers.conf against real-format Cassandra log lines.

Fluent Bit uses Onigmo (Ruby-style) regexes with (?<name>...) groups. Python
spells named groups (?P<name>...), so the patterns are translated before use;
everything else in these patterns behaves the same in both engines.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PARSERS = Path(__file__).resolve().parents[1] / "fluent-bit" / "parsers.conf"


def _to_python(pattern: str) -> re.Pattern:
    return re.compile(re.sub(r"\(\?<(?=[A-Za-z])", "(?P<", pattern))


def _load():
    text = PARSERS.read_text()
    regex = re.search(r"^\s*Regex\s+(.+)$", text, re.MULTILINE).group(1).strip()
    rules = dict(re.findall(r'rule\s+"([^"]+)"\s+"/(.+?)/"', text))
    return _to_python(regex), _to_python(rules["start_state"]), _to_python(rules["cont"])


ENTRY, START, CONT = _load()

SAMPLES = [
    ("INFO  [main] 2026-11-09 18:42:07,513 StorageService.java:1645 - JOINING: waiting for ring information",
     {"level": "INFO", "thread": "main", "source": "StorageService.java", "line": "1645",
      "message": "JOINING: waiting for ring information"}),
    ("WARN  [Native-Transport-Requests-1] 2026-11-09 18:50:12,004 BatchStatement.java:301 - Unlogged batch covering 40 partitions detected",
     {"level": "WARN", "thread": "Native-Transport-Requests-1", "source": "BatchStatement.java", "line": "301"}),
    ("INFO  [GossipStage:1] 2026-11-09 18:55:40,117 Gossiper.java:1352 - InetAddress /172.18.0.3:7000 is now DOWN",
     {"level": "INFO", "thread": "GossipStage:1", "source": "Gossiper.java",
      "message": "InetAddress /172.18.0.3:7000 is now DOWN"}),
    ("ERROR [CompactionExecutor:4] 2026-11-09 19:01:02,900 CassandraDaemon.java:581 - Exception in thread Thread[CompactionExecutor:4,1,main]",
     {"level": "ERROR", "thread": "CompactionExecutor:4", "line": "581"}),
]


@pytest.mark.parametrize("line,expected", SAMPLES)
def test_entry_regex_extracts_fields(line, expected):
    match = ENTRY.match(line)
    assert match, line
    for key, value in expected.items():
        assert match.group(key) == value
    assert match.group("time").startswith("2026-11-09 ")


def test_message_keeps_joined_stack_trace():
    entry = (
        "ERROR [ReadStage-2] 2026-11-09 19:03:11,250 AbstractLocalAwareExecutorService.java:166 - Uncaught exception\n"
        "java.lang.RuntimeException: boom\n"
        "\tat org.apache.cassandra.db.ReadCommand.executeLocally(ReadCommand.java:405)\n"
        "Caused by: java.io.IOException: disk full"
    )
    match = ENTRY.match(entry)
    assert match
    assert match.group("message").startswith("Uncaught exception\njava.lang.RuntimeException")
    assert match.group("message").endswith("disk full")


@pytest.mark.parametrize("line", [s[0] for s in SAMPLES])
def test_new_entries_start_a_multiline_record(line):
    assert START.match(line)
    assert not CONT.match(line)


@pytest.mark.parametrize("line", [
    "\tat org.apache.cassandra.db.ReadCommand.executeLocally(ReadCommand.java:405)",
    "Caused by: java.io.IOException: disk full",
    "java.lang.RuntimeException: boom",
    "    ... 12 common frames omitted",
])
def test_stack_trace_lines_continue_the_record(line):
    assert CONT.match(line)
    assert not START.match(line)


def test_non_log_text_does_not_parse_as_entry():
    assert not ENTRY.match("Picked up JAVA_TOOL_OPTIONS: -Xmx512m")
