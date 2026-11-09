from datetime import datetime, timedelta, timezone

import pytest

from loghub.timeparse import parse_duration, to_timestamp

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("text,expected", [
    ("30s", timedelta(seconds=30)),
    ("15m", timedelta(minutes=15)),
    ("2h", timedelta(hours=2)),
    ("1d", timedelta(days=1)),
    ("1w", timedelta(weeks=1)),
    (" 5M ", timedelta(minutes=5)),
])
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["", "15", "m", "1y", "-5m", "0m", "two hours"])
def test_parse_duration_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_relative_timestamp():
    assert to_timestamp("90m", NOW) == "2026-11-09T18:30:00+00:00"


def test_iso_time_without_offset_is_treated_as_utc():
    assert to_timestamp("2026-11-09T18:00:00", NOW) == "2026-11-09T18:00:00+00:00"


def test_iso_time_with_offset_is_converted_to_utc():
    assert to_timestamp("2026-11-09T10:00:00-08:00", NOW) == "2026-11-09T18:00:00+00:00"


def test_garbage_time_is_rejected():
    with pytest.raises(ValueError):
        to_timestamp("yesterday", NOW)
