from __future__ import annotations

from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import Profile
from app.ranking import upsert_rating_snapshot
from app.settings import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


@celery_app.task(name="app.tasks.recalculate_all_ratings")
def recalculate_all_ratings() -> dict[str, int]:
    """
    Periodic Stage 4 task: refresh global profile rating snapshots from DB state.
    Viewer-specific feed scores are still computed online per user.
    """
    db = SessionLocal()
    updated = 0
    try:
        profiles = db.scalars(select(Profile).where(Profile.is_active.is_(True))).all()
        for profile in profiles:
            upsert_rating_snapshot(db, candidate_profile=profile)
            updated += 1
        db.commit()
        return {"updated": updated}
    finally:
        db.close()


@celery_app.task(name="app.tasks.clear_stale_feed_cache")
def clear_stale_feed_cache() -> dict[str, int]:
    """
    Redis lists already have TTL; this task is an operational safety net for
    old keys created before TTL or left by interrupted development runs.
    """
    if redis is None:
        return {"deleted": 0}

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    deleted = 0
    for key in client.scan_iter(match="user:*:feed*"):
        ttl = client.ttl(key)
        if ttl == -1:
            client.expire(key, settings.feed_cache_ttl_seconds)
        if ttl == -2:
            deleted += 1
    return {"deleted": deleted}
