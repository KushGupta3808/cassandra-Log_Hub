# Cassandra Log Hub

A centralized place to **store, filter and view logs from a distributed Cassandra cluster**.

Each Cassandra node writes its own `system.log`, so investigating a problem normally means
opening a shell on every node and grepping files one at a time. Cassandra Log Hub collects the logs
from all nodes into one searchable index and gives you two ways to explore them: OpenSearch
Dashboards in the browser, and `logq`, a command-line tool for searching, summarizing and tailing.

```
 cassandra-1 ─┐ system.log
 cassandra-2 ─┼────────────▶ Fluent Bit ──────────▶ OpenSearch ◀── logq (CLI)
 cassandra-3 ─┘             tail, join stack        daily indices     │
                            traces, parse fields,   7-day retention   └─ OpenSearch Dashboards
                            tag node name                                  (Discover, filters)
```

## What it does

- **Runs a real 3-node Cassandra cluster** (Cassandra 4.1, one data centre, replication factor 3) in Docker Compose.
- **Collects every node's logs with Fluent Bit.** Java stack traces are joined back onto the entry that
  produced them, and each entry is split into `level`, `thread`, `source` file, `line`, `message` and timestamp.
  Every record is tagged with the `node` it came from.
- **Indexes the logs in OpenSearch** in daily `cassandra-logs-YYYY.MM.DD` indices. An index template makes
  `level`, `node`, `thread` and `source` exact-match fields, and a retention policy deletes indices after 7 days.
- **Lets you explore them** in OpenSearch Dashboards (the index pattern is created automatically) or with `logq`.
- **Generates realistic activity** on demand: writes, an oversized unlogged batch and a tombstone-heavy read,
  which make Cassandra produce real WARN entries to investigate.

## Quick start

Requirements: Docker Desktop (or Docker Engine with Compose v2) with about **6 GB of memory** available,
and Python 3.10+ for `logq`.

```bash
git clone https://github.com/KushGupta3808/cassandra-log-hub.git
cd cassandra-log-hub
docker compose up -d
```

The three Cassandra nodes start one after another (each waits for the previous one to be healthy),
so the full cluster takes a few minutes. Check progress with:

```bash
docker compose ps
docker compose exec cassandra-1 nodetool status   # all three nodes should show UN (Up/Normal)
```

Install the CLI:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

### OpenSearch on Linux or WSL2

OpenSearch needs a higher memory-map limit than the Linux default. If the `opensearch` container exits
right after starting, run this once and start the stack again:

```bash
sudo sysctl -w vm.max_map_count=262144                       # Linux
wsl -d docker-desktop sh -c "sysctl -w vm.max_map_count=262144"   # Windows (Docker Desktop on WSL2)
```

## Using it

### 1. Generate some activity

```bash
python scripts/generate_activity.py            # schema, writes, oversized batch, tombstones
```

### 2. Search with `logq`

```bash
logq search --level WARN --since 15m                  # warnings and errors from all nodes
logq search --node cassandra-2 --grep "is now DOWN"   # one node, one phrase
logq search --source BatchStatement.java --limit 20   # entries from one Java class
logq search --thread CompactionExecutor --since 1h    # one thread pool
logq stats --since 24h                                # entry counts per node and level
logq tail --level WARN                                # follow new warnings across the cluster
```

`--since` and `--until` accept durations (`30s`, `15m`, `2h`, `1d`, `1w`) or ISO times
(`2026-11-09T18:00:00`). Point `logq` at a different OpenSearch with `--url` or the
`LOGHUB_OPENSEARCH_URL` environment variable.

### 3. Browse in OpenSearch Dashboards

Open http://localhost:5601 and go to **Discover**. The `cassandra-logs-*` index pattern is already set up.
Useful filters: `level:WARN or level:ERROR`, `node:cassandra-2`, `source:Gossiper.java`.

### 4. Investigate a node failure

```bash
docker compose stop cassandra-3
logq tail --grep "is now DOWN"        # the other nodes report cassandra-3 as down
docker compose start cassandra-3      # ...and back up again
logq search --grep "is now UP" --since 10m
```

## Design decisions

| Decision | Why |
|---|---|
| **Fluent Bit** as the collector | Small memory footprint next to Cassandra's JVM, native tailing with checkpointing (no duplicates after a restart), multiline support for Java stack traces. |
| **One input per node** instead of a wildcard path | The node name becomes an exact field on every record instead of being parsed out of a file path. |
| **Index template installed before shipping starts** | Without it, OpenSearch maps `level` and `node` as analyzed text and exact filters such as `level:WARN` stop matching. A one-shot init container installs it, and Fluent Bit waits for that container to finish. |
| **Daily indices with 7-day retention** | Old logs are dropped by deleting whole indices, which is far cheaper than deleting documents. |
| **Query building separate from HTTP** | `loghub/query.py` turns filters into OpenSearch query DSL with no network calls, so every filter combination is unit tested. |
| **Parser regexes tested in Python** | `tests/test_fluent_bit_parsers.py` reads the regexes straight from `fluent-bit/parsers.conf` and checks them against real-format Cassandra lines, so a parser change cannot silently break field extraction. |

## Project layout

```
docker-compose.yml          3 Cassandra nodes, OpenSearch, Dashboards, Fluent Bit, init containers
fluent-bit/                 Fluent Bit pipeline and Cassandra log parsers
opensearch/                 index template, retention policy, init scripts
loghub/                     logq CLI: query builder, OpenSearch client, commands
scripts/generate_activity.py  realistic cluster activity for testing
tests/                      unit tests (pytest), run in CI on every push
.github/workflows/ci.yml    lint, tests, Compose and Fluent Bit config validation
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -v
```

## Scope and limitations

This is a local development setup: OpenSearch runs as a single node with the security plugin disabled,
so it should not be exposed beyond your machine. A production deployment would enable TLS and
authentication, run OpenSearch with replicas, and ship logs from each Cassandra host rather than through
shared Docker volumes.

## License

MIT
