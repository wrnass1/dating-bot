from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.settings import settings

logger = logging.getLogger("mq")


def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    """
    Publish product events to RabbitMQ (separate from Celery broker).
    Best-effort: API must not fail if broker is temporarily unavailable.
    """
    if not settings.enable_mq_publish:
        return

    try:
        import pika  # type: ignore
    except Exception:
        logger.warning("pika is not installed; skipping MQ publish")
        return

    body = {
        "event_type": event_type,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        params = pika.URLParameters(settings.rabbitmq_url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=settings.rabbitmq_events_queue, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=settings.rabbitmq_events_queue,
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )
        connection.close()
        logger.info("Published MQ event %s", event_type)
    except Exception:
        logger.exception("Failed to publish MQ event %s", event_type)
