"""Generate realistic Cassandra activity so the logs have something worth searching.

It runs CQL through `cqlsh` inside the cassandra-1 container, so no Python
Cassandra driver is needed. Scenarios:

  * schema    - create a keyspace replicated to all 3 nodes and a table
  * writes    - insert rows across many partitions
  * batch     - send an oversized unlogged batch across partitions, which makes
                Cassandra log WARN entries about batch size and partition count
  * tombstone - delete many rows in one partition and read it back, which makes
                Cassandra log a WARN about scanning tombstones

Usage:
    python scripts/generate_activity.py            # run every scenario
    python scripts/generate_activity.py batch      # run one scenario
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid

KEYSPACE = "loghub_demo"


def cql_schema() -> str:
    return f"""
CREATE KEYSPACE IF NOT EXISTS {KEYSPACE}
  WITH replication = {{'class': 'NetworkTopologyStrategy', 'dc1': 3}};
CREATE TABLE IF NOT EXISTS {KEYSPACE}.render_jobs (
  shot_id text,
  frame int,
  status text,
  payload text,
  PRIMARY KEY (shot_id, frame)
);
"""


def cql_writes(rows: int) -> str:
    lines = [
        f"INSERT INTO {KEYSPACE}.render_jobs (shot_id, frame, status, payload) "
        f"VALUES ('shot_{i % 50:03d}', {i}, 'done', '{uuid.uuid4().hex}');"
        for i in range(rows)
    ]
    return "\n".join(lines)


def cql_large_batch(partitions: int = 40, payload_bytes: int = 400) -> str:
    """An unlogged batch spanning many partitions and well over the 5 KiB warn threshold."""
    filler = "x" * payload_bytes
    inserts = "\n".join(
        f"  INSERT INTO {KEYSPACE}.render_jobs (shot_id, frame, status, payload) "
        f"VALUES ('batch_shot_{p:03d}', 1, 'queued', '{filler}');"
        for p in range(partitions)
    )
    return f"BEGIN UNLOGGED BATCH\n{inserts}\nAPPLY BATCH;"


def cql_tombstones(deletes: int = 1500) -> str:
    """Write then delete many rows in one partition, then read it back.

    Reading past more than 1,000 tombstones (Cassandra's default warn threshold)
    produces a WARN entry in system.log.
    """
    shot = "tombstone_shot"
    inserts = [
        f"INSERT INTO {KEYSPACE}.render_jobs (shot_id, frame, status) VALUES ('{shot}', {i}, 'tmp');"
        for i in range(deletes)
    ]
    removes = [f"DELETE FROM {KEYSPACE}.render_jobs WHERE shot_id = '{shot}' AND frame = {i};"
               for i in range(deletes)]
    read = f"SELECT * FROM {KEYSPACE}.render_jobs WHERE shot_id = '{shot}';"
    return "\n".join(inserts + removes + [read])


def run_cql(cql: str, node: str) -> None:
    command = ["docker", "compose", "exec", "-T", node, "cqlsh"]
    result = subprocess.run(command, input=cql, text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"cqlsh failed on {node} (exit {result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", nargs="?", default="all",
                        choices=["all", "schema", "writes", "batch", "tombstone"])
    parser.add_argument("--rows", type=int, default=500, help="rows for the writes scenario")
    parser.add_argument("--node", default="cassandra-1", help="container to run cqlsh in")
    args = parser.parse_args()

    steps = {
        "schema": cql_schema,
        "writes": lambda: cql_writes(args.rows),
        "batch": cql_large_batch,
        "tombstone": cql_tombstones,
    }
    chosen = list(steps) if args.scenario == "all" else ["schema", args.scenario]
    for name in dict.fromkeys(chosen):
        print(f"Running {name} ...", flush=True)
        run_cql(steps[name](), args.node)
    print("Done. Try: logq search --level WARN --since 15m")


if __name__ == "__main__":
    main()
