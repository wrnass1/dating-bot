from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aio_pika


@dataclass(frozen=True)
class RabbitMQBroker:
    url: str
    queue_name: str
    prefetch: int = 200

    async def setup(self) -> None:
        connection = await aio_pika.connect_robust(self.url)
        try:
            channel = await connection.channel()
            await channel.declare_queue(self.queue_name, durable=False, auto_delete=False)
        finally:
            await connection.close()

    async def producer_publish(self, payload: bytes) -> None:
        connection = await aio_pika.connect_robust(self.url)
        channel = await connection.channel(publisher_confirms=False)
        await channel.declare_queue(self.queue_name, durable=False, auto_delete=False)
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=payload,
                    delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
                ),
                routing_key=self.queue_name,
            )
        finally:
            await connection.close()

    async def create_producer(self) -> "RabbitMQProducer":
        connection = await aio_pika.connect_robust(self.url)
        channel = await connection.channel(publisher_confirms=False)
        await channel.declare_queue(self.queue_name, durable=False, auto_delete=False)
        return RabbitMQProducer(connection=connection, channel=channel, queue_name=self.queue_name)

    async def create_consumer(self) -> "RabbitMQConsumer":
        connection = await aio_pika.connect_robust(self.url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=self.prefetch)
        queue = await channel.declare_queue(self.queue_name, durable=False, auto_delete=False)
        return RabbitMQConsumer(connection=connection, channel=channel, queue=queue)


@dataclass
class RabbitMQProducer:
    connection: aio_pika.RobustConnection
    channel: aio_pika.Channel
    queue_name: str

    async def publish(self, payload: bytes) -> None:
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=payload, delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT),
            routing_key=self.queue_name,
        )

    async def close(self) -> None:
        await self.connection.close()


@dataclass
class RabbitMQConsumer:
    connection: aio_pika.RobustConnection
    channel: aio_pika.Channel
    queue: aio_pika.Queue

    async def iter_messages(self):
        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                yield message

    async def close(self) -> None:
        await self.connection.close()


async def wait_for_broker(url: str, timeout_s: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last_exc: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            connection = await aio_pika.connect_robust(url)
            await connection.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.25)
    raise RuntimeError(f"RabbitMQ not ready after {timeout_s}s: {last_exc}")

