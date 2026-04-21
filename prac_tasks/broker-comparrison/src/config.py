from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunConfig:
    broker: str  # "rabbitmq" | "redis"
    duration_s: float
    producers: int
    consumers: int
    target_msg_per_sec: int
    payload_bytes: int

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue: str = "bench.q"

    redis_url: str = "redis://localhost:6379/0"
    redis_stream: str = "bench.stream"
    redis_group: str = "bench.group"

