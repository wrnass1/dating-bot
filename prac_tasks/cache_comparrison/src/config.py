from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunConfig:
    strategy: str
    profile: str
    duration_s: float = 20.0
    dataset_size: int = 1000
    key_space: int = 200
    redis_url: str = "redis://localhost:6380/0"
    postgres_dsn: str = "dbname=cache_lab user=app password=app host=localhost port=5434"
    seed: int = 42
    cache_ttl_s: int = 300
    write_back_flush_interval_s: float = 0.5
    write_back_batch_size: int = 200


PROFILE_READ_RATIO = {
    "read-heavy": 0.80,
    "balanced": 0.50,
    "write-heavy": 0.20,
}


VALID_STRATEGIES = {"cache-aside", "write-through", "write-back"}
