import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_activity.py"
spec = importlib.util.spec_from_file_location("generate_activity", SCRIPT)
activity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activity)


def test_schema_replicates_to_all_three_nodes():
    assert "'dc1': 3" in activity.cql_schema()


def test_large_batch_exceeds_cassandra_warn_thresholds():
    cql = activity.cql_large_batch()
    assert cql.startswith("BEGIN UNLOGGED BATCH")
    # Default warn thresholds: 5 KiB batch size, 10 partitions in an unlogged batch.
    assert len(cql.encode()) > 5 * 1024
    assert cql.count("INSERT") > 10
    # Stay under the 50 KiB batch_size_fail_threshold so the batch still succeeds.
    assert len(cql.encode()) < 50 * 1024


def test_tombstone_scenario_crosses_the_warn_threshold():
    cql = activity.cql_tombstones()
    assert cql.count("DELETE FROM") > 1000
    assert cql.rstrip().endswith(";") and "SELECT * FROM" in cql


def test_writes_spread_across_partitions():
    cql = activity.cql_writes(120)
    assert cql.count("INSERT") == 120
    assert "'shot_049'" in cql and "'shot_050'" not in cql
