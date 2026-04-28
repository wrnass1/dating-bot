from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Reservoir:
    max_samples: int = 200_000

    def __post_init__(self) -> None:
        self._samples: list[float] = []
        self._seen: int = 0

    def add(self, value: float) -> None:
        self._seen += 1
        if len(self._samples) < self.max_samples:
            self._samples.append(value)
            return
        j = random.randint(1, self._seen)
        if j <= self.max_samples:
            self._samples[j - 1] = value

    def count_seen(self) -> int:
        return self._seen

    def snapshot(self) -> list[float]:
        return list(self._samples)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values_sorted[int(k)]
    d0 = values_sorted[f] * (c - k)
    d1 = values_sorted[c] * (k - f)
    return d0 + d1


def mean(values: list[float]) -> float:
    if not values:
        return math.nan
    return sum(values) / len(values)
