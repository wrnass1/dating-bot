from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass

from redis import Redis

from .config import PROFILE_READ_RATIO, RunConfig, VALID_STRATEGIES
from .db import PostgresStore
from .metrics import Reservoir, mean, percentile
from .strategies import make_strategy


@dataclass
class BenchResult:
    strategy: str
    profile: str
    duration_s: float
    dataset_size: int
    key_space: int
    total_ops: int
    read_ops: int
    write_ops: int
    throughput_req_s: float
    latency_ms_mean: float
    latency_ms_p95: float
    db_reads: int
    db_writes: int
    db_total_ops: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    write_back_flushes: int
    write_back_items_flushed: int
    write_back_pending_max: int
    write_back_pending_final: int

    def to_dict(self) -> dict:
        return asdict(self)


def init_db(cfg: RunConfig) -> None:
    store = PostgresStore(cfg.postgres_dsn)
    try:
        store.init_schema()
        store.seed(cfg.dataset_size)
    finally:
        store.close()


def run_benchmark(cfg: RunConfig) -> BenchResult:
    if cfg.strategy not in VALID_STRATEGIES:
        raise ValueError(f"strategy must be one of {sorted(VALID_STRATEGIES)}")
    if cfg.profile not in PROFILE_READ_RATIO:
        raise ValueError(f"profile must be one of {sorted(PROFILE_READ_RATIO)}")
    if cfg.key_space < 1 or cfg.key_space > cfg.dataset_size:
        raise ValueError("key_space must be between 1 and dataset_size")

    random_gen = random.Random(cfg.seed)
    read_ratio = PROFILE_READ_RATIO[cfg.profile]

    store = PostgresStore(cfg.postgres_dsn)
    redis_client = Redis.from_url(cfg.redis_url, decode_responses=True)
    namespace = f"cache-lab:{cfg.strategy}:{cfg.profile}"
    strategy = make_strategy(
        name=cfg.strategy,
        redis_client=redis_client,
        store=store,
        namespace=namespace,
        cache_ttl_s=cfg.cache_ttl_s,
        flush_interval_s=cfg.write_back_flush_interval_s,
        batch_size=cfg.write_back_batch_size,
    )
    strategy.clear()
    store.init_schema()
    store.seed(cfg.dataset_size)

    latencies = Reservoir()
    read_ops = 0
    write_ops = 0
    total_ops = 0
    started_at = time.perf_counter()

    try:
        while True:
            now = time.perf_counter()
            if now - started_at >= cfg.duration_s:
                break
            item_id = random_gen.randint(1, cfg.key_space)
            op_started = time.perf_counter()
            if random_gen.random() < read_ratio:
                strategy.read(item_id)
                read_ops += 1
            else:
                new_value = random_gen.randint(1, 1_000_000)
                strategy.write(item_id, new_value)
                write_ops += 1
            latencies.add((time.perf_counter() - op_started) * 1000.0)
            total_ops += 1
    finally:
        wb_stats = strategy.shutdown()
        store.close()

    elapsed = max(time.perf_counter() - started_at, 1e-9)
    wb_flushes = 0
    wb_items_flushed = 0
    wb_pending_max = 0
    wb_pending_final = 0
    if wb_stats is not None:
        wb_flushes = wb_stats.flushes
        wb_items_flushed = wb_stats.items_flushed
        wb_pending_max = wb_stats.pending_max
        wb_pending_final = wb_stats.pending_final

    return BenchResult(
        strategy=cfg.strategy,
        profile=cfg.profile,
        duration_s=cfg.duration_s,
        dataset_size=cfg.dataset_size,
        key_space=cfg.key_space,
        total_ops=total_ops,
        read_ops=read_ops,
        write_ops=write_ops,
        throughput_req_s=total_ops / elapsed,
        latency_ms_mean=mean(latencies.snapshot()),
        latency_ms_p95=percentile(latencies.snapshot(), 95.0),
        db_reads=store.counters.reads,
        db_writes=store.counters.writes,
        db_total_ops=store.counters.total,
        cache_hits=strategy.counters.hits,
        cache_misses=strategy.counters.misses,
        cache_hit_rate=strategy.counters.hit_rate,
        write_back_flushes=wb_flushes,
        write_back_items_flushed=wb_items_flushed,
        write_back_pending_max=wb_pending_max,
        write_back_pending_final=wb_pending_final,
    )
