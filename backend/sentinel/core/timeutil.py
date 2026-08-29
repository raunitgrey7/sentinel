"""UTC time helpers. All timestamps in Sentinel are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_ts(value: str | float | int | datetime | None) -> datetime:
    """Parse ISO-8601 strings, epoch seconds/millis/nanos, or datetimes into UTC."""
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return ensure_utc(value)  # type: ignore[return-value]
    if isinstance(value, int | float):
        v = float(value)
        if v > 1e17:  # nanoseconds
            v /= 1e9
        elif v > 1e14:  # microseconds
            v /= 1e6
        elif v > 1e11:  # milliseconds
            v /= 1e3
        return datetime.fromtimestamp(v, UTC)
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(s))  # type: ignore[return-value]


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)


def seconds(n: float) -> timedelta:
    return timedelta(seconds=n)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else ensure_utc(dt).isoformat()  # type: ignore[union-attr]
