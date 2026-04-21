from __future__ import annotations

import asyncio
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.asyncio.client import Redis as RedisClient


@dataclass(frozen=True)
class RedisStreamBroker:
    url: str
    stream: str
    group: str

    async def setup(self) -> None:
        r: RedisClient = Redis.from_url(self.url, decode_responses=False)
        try:
            # Keep runs comparable: start from empty stream, recreate group
            try:
                await r.delete(self.stream)
            except Exception:  # noqa: BLE001
                pass
            try:
                await r.xgroup_create(name=self.stream, groupname=self.group, id="0-0", mkstream=True)
            except Exception:  # noqa: BLE001
                # Group may already exist; ignore
                pass
        finally:
            await r.aclose()

    async def create_producer(self) -> "RedisProducer":
        r: RedisClient = Redis.from_url(self.url, decode_responses=False)
        return RedisProducer(r=r, stream=self.stream)

    async def create_consumer(self, consumer_name: str) -> "RedisConsumer":
        r: RedisClient = Redis.from_url(self.url, decode_responses=False)
        return RedisConsumer(r=r, stream=self.stream, group=self.group, consumer=consumer_name)


@dataclass
class RedisProducer:
    r: RedisClient
    stream: str

    async def publish(self, payload: bytes) -> None:
        # Single field keeps format stable
        await self.r.xadd(self.stream, {"b": payload})

    async def close(self) -> None:
        await self.r.aclose()


@dataclass
class RedisConsumer:
    r: RedisClient
    stream: str
    group: str
    consumer: str

    async def read(self, *, count: int = 200, block_ms: int = 1000):
        return await self.r.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={self.stream: ">"},
            count=count,
            block=block_ms,
        )

    async def ack(self, message_id: bytes) -> None:
        await self.r.xack(self.stream, self.group, message_id)

    async def close(self) -> None:
        await self.r.aclose()


async def wait_for_broker(url: str, timeout_s: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last_exc: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            r: RedisClient = Redis.from_url(url, decode_responses=False)
            await r.ping()
            await r.aclose()
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.25)
    raise RuntimeError(f"Redis not ready after {timeout_s}s: {last_exc}")

