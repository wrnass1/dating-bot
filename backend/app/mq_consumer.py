from __future__ import annotations

import json
import logging
import sys

from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mq_consumer")


def _handle_event(event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    logger.info("Consumed event=%s payload=%s", event_type, payload)

    if event_type in ("profile_liked", "profile_skipped", "match_created"):
        from app.db import SessionLocal
        from app.models import Profile
        from app.ranking import upsert_rating_snapshot
        from sqlalchemy import select

        profile_id = payload.get("to_profile_id")
        if not profile_id:
            return
        db = SessionLocal()
        try:
            prof = db.scalar(select(Profile).where(Profile.id == profile_id))
            if prof is not None:
                upsert_rating_snapshot(db, candidate_profile=prof)
                db.commit()
                logger.info("Refreshed rating snapshot for profile %s", profile_id)
        finally:
            db.close()


def main() -> None:
    import pika  # type: ignore

    params = pika.URLParameters(settings.rabbitmq_url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=settings.rabbitmq_events_queue, durable=True)
    logger.info("Listening on queue %s", settings.rabbitmq_events_queue)

    def callback(ch, method, properties, body):  # noqa: ANN001
        try:
            event = json.loads(body.decode("utf-8"))
            _handle_event(event)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception("Failed to process message")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=settings.rabbitmq_events_queue, on_message_callback=callback)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Shutting down consumer")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("MQ consumer failed to start")
        sys.exit(1)
