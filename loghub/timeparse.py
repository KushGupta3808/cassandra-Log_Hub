"""Parse relative durations such as "15m" or "2h" used by --since and --until."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_DURATION = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)


def parse_duration(text: str) -> timedelta:
    """Turn "30s", "15m", "2h", "1d" or "1w" into a timedelta.

    Raises ValueError for anything else, including zero or negative values.
    """
    match = _DURATION.match(text or "")
    if not match:
        raise ValueError(f"invalid duration {text!r}; use a number and a unit, e.g. 15m, 2h, 1d")
    amount, unit = int(match.group(1)), match.group(2).lower()
    if amount == 0:
        raise ValueError("duration must be greater than zero")
    return timedelta(**{_UNITS[unit]: amount})


def to_timestamp(value: str, now: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp for a relative duration or an ISO date/time.

    "15m" means 15 minutes before now; "2026-11-09T18:00:00" is used as given
    (treated as UTC when it has no offset).
    """
    now = now or datetime.now(timezone.utc)
    try:
        return (now - parse_duration(value)).isoformat()
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid time {value!r}; use a duration like 15m or an ISO time") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()
