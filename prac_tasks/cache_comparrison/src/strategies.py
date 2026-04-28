from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from redis import Redis

from .db import PostgresStore


@dataclass
class CacheCounters:
    hits: int = 0
    misses: int = 0

    @property
    def total_reads(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_reads == 0:
            return 0.0
        return self.hits / self.total_reads


@dataclass
class WriteBackStats:
    flushes: int = 0
    items_flushed: int = 0
    pending_max: int = 0
    pending_final: int = 0


class BaseStrategy:
    def __init__(self, redis_client: Redis, store: PostgresStore, namespace: str, cache_ttl_s: int) -> None:
        self.redis = redis_client
        self.store = store
        self.namespace = namespace
        self.cache_ttl_s = cache_ttl_s
        self.counters = CacheCounters()

    def cache_key(self, item_id: int) -> str:
        return f"{self.namespace}:item:{item_id}"

    def clear(self) -> None:
        keys = self.redis.keys(f"{self.namespace}:*")
        if keys:
            self.redis.delete(*keys)

    def read(self, item_id: int) -> int:
        raise NotImplementedError

    def write(self, item_id: int, value: int) -> None:
        raise NotImplementedError

    def shutdown(self) -> WriteBackStats | None:
        return None

    def _get_cached_value(self, item_id: int) -> int | None:
        raw = self.redis.get(self.cache_key(item_id))
        if raw is None:
            self.counters.misses += 1
            return None
        self.counters.hits += 1
        return int(raw)

    def _set_cached_value(self, item_id: int, value: int) -> None:
        self.redis.set(self.cache_key(item_id), value, ex=self.cache_ttl_s)


class CacheAsideStrategy(BaseStrategy):
    def read(self, item_id: int) -> int:
        cached = self._get_cached_value(item_id)
        if cached is not None:
            return cached
        value = self.store.read(item_id)
        self._set_cached_value(item_id, value)
        return value

    def write(self, item_id: int, value: int) -> None:
        self.store.write(item_id, value)
        self.redis.delete(self.cache_key(item_id))


class WriteThroughStrategy(BaseStrategy):
    def read(self, item_id: int) -> int:
        cached = self._get_cached_value(item_id)
        if cached is not None:
            return cached
        value = self.store.read(item_id)
        self._set_cached_value(item_id, value)
        return value

    def write(self, item_id: int, value: int) -> None:
        self.store.write(item_id, value)
        self._set_cached_value(item_id, value)


class WriteBackStrategy(BaseStrategy):
    def __init__(
        self,
        redis_client: Redis,
        store: PostgresStore,
        namespace: str,
        cache_ttl_s: int,
        flush_interval_s: float,
        batch_size: int,
    ) -> None:
        super().__init__(redis_client, store, namespace, cache_ttl_s)
        self.flush_interval_s = flush_interval_s
        self.batch_size = batch_size
        self._dirty_hash = f"{namespace}:dirty"
        self._dirty_queue = f"{namespace}:dirty_queue"
        self._stats = WriteBackStats()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def clear(self) -> None:
        super().clear()
        self.redis.delete(self._dirty_hash, self._dirty_queue)

    def read(self, item_id: int) -> int:
        cached = self._get_cached_value(item_id)
        if cached is not None:
            return cached
        value = self.store.read(item_id)
        self._set_cached_value(item_id, value)
        return value

    def write(self, item_id: int, value: int) -> None:
        self._set_cached_value(item_id, value)
        pipe = self.redis.pipeline()
        pipe.hset(self._dirty_hash, item_id, value)
        pipe.zadd(self._dirty_queue, {str(item_id): time.time()})
        pipe.execute()
        pending = self.redis.zcard(self._dirty_queue)
        if pending > self._stats.pending_max:
            self._stats.pending_max = int(pending)

    def shutdown(self) -> WriteBackStats:
        self._stop.set()
        self._thread.join(timeout=5.0)
        self._flush_once(force_all=True)
        self._stats.pending_final = int(self.redis.zcard(self._dirty_queue))
        return self._stats

    def _flush_loop(self) -> None:
        while not self._stop.wait(self.flush_interval_s):
            self._flush_once(force_all=False)

    def _flush_once(self, force_all: bool) -> None:
        count = self.batch_size if not force_all else -1
        if count == -1:
            members = self.redis.zrange(self._dirty_queue, 0, -1)
        else:
            members = self.redis.zrange(self._dirty_queue, 0, max(0, count - 1))
        if not members:
            return
        self._stats.flushes += 1
        for raw_member in members:
            item_id = int(raw_member)
            raw_value = self.redis.hget(self._dirty_hash, item_id)
            if raw_value is None:
                self.redis.zrem(self._dirty_queue, raw_member)
                continue
            self.store.write(item_id, int(raw_value))
            pipe = self.redis.pipeline()
            pipe.hdel(self._dirty_hash, item_id)
            pipe.zrem(self._dirty_queue, raw_member)
            pipe.execute()
            self._stats.items_flushed += 1


def make_strategy(name: str, redis_client: Redis, store: PostgresStore, namespace: str, cache_ttl_s: int, flush_interval_s: float, batch_size: int) -> BaseStrategy:
    if name == "cache-aside":
        return CacheAsideStrategy(redis_client, store, namespace, cache_ttl_s)
    if name == "write-through":
        return WriteThroughStrategy(redis_client, store, namespace, cache_ttl_s)
    if name == "write-back":
        return WriteBackStrategy(redis_client, store, namespace, cache_ttl_s, flush_interval_s, batch_size)
    raise ValueError(f"Unknown strategy: {name}")
