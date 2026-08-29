"""Deterministic statistics used by the investigators.

No numpy: the series are short (minutes of 5-second samples) and keeping the analysis
layer dependency-free keeps it easy to reason about and test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sentinel.telemetry.store import Point


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


@dataclass(slots=True)
class Deviation:
    metric: str
    baseline_mean: float
    baseline_std: float
    incident_mean: float
    incident_max: float
    incident_last: float
    pct_change: float  # (incident_mean - baseline_mean) / |baseline_mean|
    z_score: float
    direction: str  # "up" | "down" | "flat"
    samples_baseline: int
    samples_incident: int
    onset: datetime | None  # first timestamp the series crossed the deviation threshold

    def significant(self, *, z: float = 3.0, pct: float = 0.35) -> bool:
        if self.samples_incident < 2:
            return False
        return abs(self.z_score) >= z or abs(self.pct_change) >= pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "baseline_mean": round(self.baseline_mean, 4),
            "baseline_std": round(self.baseline_std, 4),
            "incident_mean": round(self.incident_mean, 4),
            "incident_max": round(self.incident_max, 4),
            "incident_last": round(self.incident_last, 4),
            "pct_change": round(self.pct_change, 4),
            "z_score": round(self.z_score, 3),
            "direction": self.direction,
            "samples_baseline": self.samples_baseline,
            "samples_incident": self.samples_incident,
            "onset": self.onset.isoformat() if self.onset else None,
        }


def deviation(metric: str, baseline: list[Point], incident: list[Point]) -> Deviation:
    b = [p.value for p in baseline]
    i = [p.value for p in incident]
    b_mean, b_std = mean(b), stdev(b)
    i_mean = mean(i)
    i_max = max(i) if i else 0.0
    i_last = i[-1] if i else 0.0
    denom = abs(b_mean) if abs(b_mean) > 1e-9 else 1e-9
    pct = (i_mean - b_mean) / denom if b else (1.0 if i_mean > 0 else 0.0)
    # Guard against a degenerate (constant) baseline: use a floor on std relative to the mean.
    std_floor = max(b_std, 0.05 * abs(b_mean), 1e-6)
    z = (i_mean - b_mean) / std_floor
    if not b and i:
        z = 3.5 if i_mean > 0 else 0.0
    z = max(-99.0, min(99.0, z))  # beyond this the number carries no information
    direction = "up" if pct > 0.1 else "down" if pct < -0.1 else "flat"
    onset = None
    thr = b_mean + 2.5 * std_floor if direction == "up" else b_mean - 2.5 * std_floor
    for p in incident:
        if (direction == "up" and p.value >= thr) or (direction == "down" and p.value <= thr):
            onset = p.ts
            break
    return Deviation(metric, b_mean, b_std, i_mean, i_max, i_last, pct, z, direction, len(b), len(i), onset)


def first_crossing(series: list[Point], threshold: float, comparator: str = ">") -> datetime | None:
    for p in series:
        if _cmp(p.value, comparator, threshold):
            return p.ts
    return None


def _cmp(v: float, comparator: str, t: float) -> bool:
    return {">": v > t, ">=": v >= t, "<": v < t, "<=": v <= t}.get(comparator, False)


def sustained(series: list[Point], threshold: float, comparator: str, for_s: int) -> tuple[bool, float | None]:
    """True if the series satisfies the comparator continuously for the trailing ``for_s`` seconds."""
    if not series:
        return False, None
    end = series[-1].ts
    window = [p for p in series if (end - p.ts).total_seconds() <= for_s]
    if not window:
        return False, None
    if (end - window[0].ts).total_seconds() < for_s * 0.6 and len(window) < 2:
        return False, None
    ok = all(_cmp(p.value, comparator, threshold) for p in window)
    return ok, window[-1].value


def correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den > 0 else 0.0
