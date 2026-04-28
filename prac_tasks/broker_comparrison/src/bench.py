from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass

from .config import RunConfig
from .message import MessageSpec, make_message_bytes, monotonic_time_ns, parse_message_bytes
from .metrics import Reservoir, mean, percentile


@dataclass
class BenchResult:
    broker: str
    duration_s: float
    producers: int
    consumers: int
    target_msg_per_sec: int
    payload_bytes: int

    sent: int
    send_errors: int
    processed: int
    process_errors: int

    throughput_msg_s: float
    latency_ms_mean: float
    latency_ms_p95: float

    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class _Counters:
    __slots__ = ("sent", "send_errors", "processed", "process_errors")

    def __init__(self) -> None:
        self.sent = 0
        self.send_errors = 0
        self.processed = 0
        self.process_errors = 0


async def run_benchmark(cfg: RunConfig) -> BenchResult:
    if cfg.broker not in {"rabbitmq", "redis"}:
        raise ValueError("broker must be 'rabbitmq' or 'redis'")
    if cfg.producers < 1 or cfg.consumers < 1:
        raise ValueError("producers/consumers must be >= 1")
    if cfg.duration_s <= 0:
        raise ValueError("duration_s must be > 0")
    if cfg.target_msg_per_sec <= 0:
        raise ValueError("target_msg_per_sec must be > 0")
    if cfg.payload_bytes < 0:
        raise ValueError("payload_bytes must be >= 0")

    counters = _Counters()
    reservoir = Reservoir(max_samples=200_000)
    stop = asyncio.Event()
    spec = MessageSpec(payload_bytes=cfg.payload_bytes)

    if cfg.broker == "rabbitmq":
        from .brokers.rabbitmq_broker import RabbitMQBroker, wait_for_broker

        await wait_for_broker(cfg.rabbitmq_url)
        broker = RabbitMQBroker(url=cfg.rabbitmq_url, queue_name=cfg.rabbitmq_queue)
        await broker.setup()

        async def producer_task(producer_idx: int) -> None:
            seq = producer_idx << 48
            p = await broker.create_producer()
            try:
                interval = 1.0 / (cfg.target_msg_per_sec / cfg.producers)
                next_t = asyncio.get_event_loop().time()
                while not stop.is_set():
                    now = asyncio.get_event_loop().time()
                    if now < next_t:
                        await asyncio.sleep(next_t - now)
                    next_t += interval
                    try:
                        msg = make_message_bytes(spec, seq)
                        await p.publish(msg)
                        counters.sent += 1
                        seq += 1
                    except Exception:  # noqa: BLE001
                        counters.send_errors += 1
            finally:
                await p.close()

        async def consumer_task(consumer_idx: int) -> None:
            c = await broker.create_consumer()
            try:
                # bounded queue.get() avoids hanging on iterator shutdown
                while not stop.is_set():
                    try:
                        message = await c.get(timeout_s=1.0)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        sent_ns, _seq, _payload = parse_message_bytes(message.body)
                        latency_ms = (monotonic_time_ns() - sent_ns) / 1_000_000.0
                        reservoir.add(latency_ms)
                        counters.processed += 1
                        await message.ack()
                    except Exception:  # noqa: BLE001
                        counters.process_errors += 1
                        try:
                            await message.nack(requeue=True)
                        except Exception:  # noqa: BLE001
                            pass
            finally:
                await c.close()

    else:
        from .brokers.redis_broker import RedisStreamBroker, wait_for_broker

        await wait_for_broker(cfg.redis_url)
        broker = RedisStreamBroker(url=cfg.redis_url, stream=cfg.redis_stream, group=cfg.redis_group)
        await broker.setup()

        async def producer_task(producer_idx: int) -> None:
            seq = producer_idx << 48
            p = await broker.create_producer()
            try:
                interval = 1.0 / (cfg.target_msg_per_sec / cfg.producers)
                next_t = asyncio.get_event_loop().time()
                while not stop.is_set():
                    now = asyncio.get_event_loop().time()
                    if now < next_t:
                        await asyncio.sleep(next_t - now)
                    next_t += interval
                    try:
                        msg = make_message_bytes(spec, seq)
                        await p.publish(msg)
                        counters.sent += 1
                        seq += 1
                    except Exception:  # noqa: BLE001
                        counters.send_errors += 1
            finally:
                await p.close()

        async def consumer_task(consumer_idx: int) -> None:
            c = await broker.create_consumer(consumer_name=f"c{consumer_idx}")
            try:
                while not stop.is_set():
                    try:
                        batches = await c.read(count=200, block_ms=500)
                        if not batches:
                            continue
                        for _stream_name, msgs in batches:
                            for msg_id, fields in msgs:
                                try:
                                    raw = fields[b"b"]
                                    sent_ns, _seq, _payload = parse_message_bytes(raw)
                                    latency_ms = (monotonic_time_ns() - sent_ns) / 1_000_000.0
                                    reservoir.add(latency_ms)
                                    counters.processed += 1
                                    await c.ack(msg_id)
                                except Exception:  # noqa: BLE001
                                    counters.process_errors += 1
                    except Exception:  # noqa: BLE001
                        await asyncio.sleep(0.1)
            finally:
                await c.close()

    producers = [asyncio.create_task(producer_task(i)) for i in range(cfg.producers)]
    consumers = [asyncio.create_task(consumer_task(i)) for i in range(cfg.consumers)]

    t0 = time.perf_counter()
    try:
        await asyncio.sleep(cfg.duration_s)
    except asyncio.CancelledError:
        raise
    finally:
        stop.set()

    await asyncio.gather(*producers, return_exceptions=True)
    # Don't let consumers hang forever after producers stop
    try:
        await asyncio.wait_for(asyncio.gather(*consumers, return_exceptions=True), timeout=5.0)
    except asyncio.TimeoutError:
        for t in consumers:
            t.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
    elapsed = time.perf_counter() - t0

    lat_samples = reservoir.snapshot()
    processed = counters.processed
    throughput = processed / elapsed if elapsed > 0 else 0.0

    return BenchResult(
        broker=cfg.broker,
        duration_s=cfg.duration_s,
        producers=cfg.producers,
        consumers=cfg.consumers,
        target_msg_per_sec=cfg.target_msg_per_sec,
        payload_bytes=cfg.payload_bytes,
        sent=counters.sent,
        send_errors=counters.send_errors,
        processed=processed,
        process_errors=counters.process_errors,
        throughput_msg_s=throughput,
        latency_ms_mean=mean(lat_samples),
        latency_ms_p95=percentile(lat_samples, 95.0),
        notes=f"latency sample size={len(lat_samples)}/{reservoir.count_seen()}",
    )

