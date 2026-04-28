from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Reservoir:
    max_samples: int = 200_000

    def __post_init__(self) -> None:
        self._samples: list[float] = []
        self._seen = 0

    def add(self, value: float) -> None:
        self._seen += 1
        if len(self._samples) < self.max_samples:
            self._samples.append(value)
            return
        index = random.randint(1, self._seen)
        if index <= self.max_samples:
            self._samples[index - 1] = value

    def snapshot(self) -> list[float]:
        return list(self._samples)


def mean(values: list[float]) -> float:
    if not values:
        return math.nan
    return sum(values) / len(values)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    values_sorted = sorted(values)
    rank = (len(values_sorted) - 1) * (p / 100.0)
    floor_rank = math.floor(rank)
    ceil_rank = math.ceil(rank)
    if floor_rank == ceil_rank:
        return values_sorted[int(rank)]
    low = values_sorted[floor_rank] * (ceil_rank - rank)
    high = values_sorted[ceil_rank] * (rank - floor_rank)
    return low + high
