from celery import Celery

from app.settings import settings


celery_app = Celery(
    "dating_bot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "recalculate-ratings-every-10-minutes": {
            "task": "app.tasks.recalculate_all_ratings",
            "schedule": 600.0,
        },
        "clear-stale-feed-cache-every-15-minutes": {
            "task": "app.tasks.clear_stale_feed_cache",
            "schedule": 900.0,
        },
    },
)
