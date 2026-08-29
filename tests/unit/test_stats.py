from datetime import UTC, datetime, timedelta

from sentinel.analysis.stats import correlation, deviation, first_crossing, percentile, sustained
from sentinel.telemetry.store import Point

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def series(values: list[float], step_s: int = 10) -> list[Point]:
    return [Point(ts=T0 + timedelta(seconds=i * step_s), value=v) for i, v in enumerate(values)]


def test_deviation_detects_spike():
    base = series([10, 11, 9, 10, 10, 11, 9, 10])
    cur = series([10, 30, 60, 90, 95, 99])
    d = deviation("db_connections_active", base, cur)
    assert d.direction == "up"
    assert d.significant()
    assert d.z_score > 3
    assert d.onset is not None


def test_deviation_flat_is_not_significant():
    base = series([100, 101, 99, 100, 100])
    cur = series([100, 100, 101, 99, 100])
    d = deviation("cpu", base, cur)
    assert d.direction == "flat"
    assert not d.significant()


def test_deviation_handles_constant_baseline():
    base = series([0, 0, 0, 0, 0])
    cur = series([0, 0.2, 0.3, 0.35])
    d = deviation("error_rate", base, cur)
    assert d.direction == "up"
    assert d.significant()


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([], 0.9) == 0.0
    assert percentile([10], 0.95) == 10


def test_sustained_and_first_crossing():
    s = series([0.01, 0.02, 0.15, 0.2, 0.25, 0.3, 0.3, 0.3])
    assert first_crossing(s, 0.1, ">") == T0 + timedelta(seconds=20)
    ok, value = sustained(s, 0.1, ">", for_s=40)
    assert ok and value == 0.3
    ok, _ = sustained(s, 0.1, ">", for_s=120)
    assert not ok  # window includes the early low values


def test_correlation():
    assert correlation([1, 2, 3, 4], [2, 4, 6, 8]) > 0.99
    assert correlation([1, 2, 3, 4], [4, 3, 2, 1]) < -0.99
    assert correlation([1, 2], [1, 2]) == 0.0
