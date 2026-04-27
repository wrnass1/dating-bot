import json
import uuid

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import and_, delete, desc, or_, select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Interaction, Match, Profile, Rating, User
from app.ranking import upsert_rating_for_pair
from app.schemas import (
    DevResetUserStateIn,
    DevResetUserStateOut,
    FeedActionIn,
    FeedActionOut,
    FeedNextIn,
    FeedProfileOut,
    InteractionIn,
    InteractionOut,
    ProfileOut,
    ProfileUpsertIn,
    TelegramUserUpsertIn,
    TelegramUserUpsertOut,
)
from app.settings import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


app = FastAPI(title="Dating Bot API", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    # For stage 2-3 we keep it simple: auto-create the table set.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/users/telegram/upsert", response_model=TelegramUserUpsertOut)
def upsert_telegram_user(payload: TelegramUserUpsertIn, db: Session = Depends(get_db)) -> TelegramUserUpsertOut:
    existing = db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if existing is None:
        user = User(
            telegram_id=payload.telegram_id,
            username=payload.username,
            first_name=payload.first_name,
            language=payload.language,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return TelegramUserUpsertOut(user_id=str(user.id), is_new=True)

    changed = False
    for field in ("username", "first_name", "language"):
        new_val = getattr(payload, field)
        if new_val is not None and getattr(existing, field) != new_val:
            setattr(existing, field, new_val)
            changed = True
    if changed:
        db.commit()

    return TelegramUserUpsertOut(user_id=str(existing.id), is_new=False)


def _get_redis():
    if redis is None:
        raise RuntimeError("Redis package is not installed")
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _get_user_by_telegram(db: Session, telegram_id: int) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found. Call /users/telegram/upsert first.")
    return user


def _get_or_create_profile(db: Session, user: User) -> Profile:
    prof = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if prof is None:
        prof = Profile(user_id=user.id, is_active=True)
        db.add(prof)
        db.flush()
    return prof


@app.post("/profiles/upsert", response_model=ProfileOut)
def upsert_profile(payload: ProfileUpsertIn, db: Session = Depends(get_db)) -> ProfileOut:
    user = _get_user_by_telegram(db, payload.telegram_id)
    prof = _get_or_create_profile(db, user)

    for field in (
        "age",
        "gender",
        "city",
        "interests",
        "about",
        "pref_gender",
        "pref_age_min",
        "pref_age_max",
        "pref_city",
        "is_active",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(prof, field, val)

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return ProfileOut(
        profile_id=str(prof.id),
        user_id=str(prof.user_id),
        is_active=bool(prof.is_active),
        age=prof.age,
        gender=prof.gender,
        city=prof.city,
        interests=prof.interests,
        about=prof.about,
        pref_gender=prof.pref_gender,
        pref_age_min=prof.pref_age_min,
        pref_age_max=prof.pref_age_max,
        pref_city=prof.pref_city,
    )


@app.get("/profiles/by_telegram/{telegram_id}", response_model=ProfileOut)
def get_profile_by_telegram(telegram_id: int, db: Session = Depends(get_db)) -> ProfileOut:
    user = _get_user_by_telegram(db, telegram_id)
    prof = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileOut(
        profile_id=str(prof.id),
        user_id=str(prof.user_id),
        is_active=bool(prof.is_active),
        age=prof.age,
        gender=prof.gender,
        city=prof.city,
        interests=prof.interests,
        about=prof.about,
        pref_gender=prof.pref_gender,
        pref_age_min=prof.pref_age_min,
        pref_age_max=prof.pref_age_max,
        pref_city=prof.pref_city,
    )


def _viewer_profile_or_400(db: Session, telegram_id: int) -> Profile:
    user = _get_user_by_telegram(db, telegram_id)
    prof = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if prof is None or not prof.is_active:
        raise HTTPException(status_code=400, detail="Viewer profile is missing or inactive")
    return prof


def _feed_key(user_id: uuid.UUID) -> str:
    return f"user:{user_id}:feed"


def _feed_meta_key(user_id: uuid.UUID) -> str:
    return f"user:{user_id}:feed:meta"


def _build_feed_batch(db: Session, *, viewer: Profile, batch_size: int = 10) -> list[str]:
    # Candidates: active profiles excluding viewer + not yet interacted by viewer.
    interacted_subq = select(Interaction.to_profile_id).where(Interaction.from_user_id == viewer.user_id).subquery()

    candidates = db.scalars(
        select(Profile)
        .where(
            Profile.is_active.is_(True),
            Profile.user_id != viewer.user_id,
            Profile.id.not_in(select(interacted_subq.c.to_profile_id)),
        )
        .limit(200)
    ).all()

    if not candidates:
        return []

    # Upsert ratings for candidates relative to viewer, then select top by combined score.
    for cand in candidates:
        upsert_rating_for_pair(db, viewer_profile=viewer, candidate_profile=cand)
    db.commit()

    top_ids = db.scalars(
        select(Profile.id)
        .join(Rating, Rating.profile_id == Profile.id)
        .where(Profile.id.in_([c.id for c in candidates]))
        .order_by(desc(Rating.combined_score), desc(Rating.updated_at))
        .limit(batch_size)
    ).all()

    return [str(x) for x in top_ids]


@app.post("/feed/next", response_model=FeedProfileOut)
def feed_next(payload: FeedNextIn, db: Session = Depends(get_db)) -> FeedProfileOut:
    viewer = _viewer_profile_or_400(db, payload.telegram_id)
    r = _get_redis()

    key = _feed_key(viewer.user_id)
    profile_id = r.lpop(key)
    if profile_id is None:
        batch = _build_feed_batch(db, viewer=viewer, batch_size=10)
        if not batch:
            raise HTTPException(status_code=404, detail="No profiles found")
        r.rpush(key, *batch)
        r.set(_feed_meta_key(viewer.user_id), json.dumps({"batch_size": len(batch)}))
        profile_id = r.lpop(key)

    pid = uuid.UUID(profile_id)
    prof = db.scalar(select(Profile).where(Profile.id == pid))
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    rating = db.scalar(select(Rating).where(Rating.profile_id == prof.id))
    combined = float(rating.combined_score) if rating is not None else 0.0

    return FeedProfileOut(
        profile_id=str(prof.id),
        user_id=str(prof.user_id),
        telegram_id=int(prof.user.telegram_id),
        age=prof.age,
        gender=prof.gender,
        city=prof.city,
        interests=prof.interests,
        about=prof.about,
        combined_score=combined,
    )


@app.post("/interactions", response_model=InteractionOut)
def create_interaction(payload: InteractionIn, db: Session = Depends(get_db)) -> InteractionOut:
    if payload.action not in ("like", "skip"):
        raise HTTPException(status_code=400, detail="action must be like|skip")

    user = _get_user_by_telegram(db, payload.telegram_id)
    viewer = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if viewer is None or not viewer.is_active:
        raise HTTPException(status_code=400, detail="Viewer profile is missing or inactive")

    try:
        to_profile_uuid = uuid.UUID(payload.to_profile_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to_profile_id") from None

    target = db.scalar(select(Profile).where(Profile.id == to_profile_uuid, Profile.is_active.is_(True)))
    if target is None:
        raise HTTPException(status_code=404, detail="Target profile not found")
    if target.user_id == viewer.user_id:
        raise HTTPException(status_code=400, detail="Cannot interact with yourself")

    existing = db.scalar(
        select(Interaction).where(Interaction.from_user_id == viewer.user_id, Interaction.to_profile_id == target.id)
    )
    if existing is None:
        db.add(Interaction(from_user_id=viewer.user_id, to_profile_id=target.id, action=payload.action))
    else:
        existing.action = payload.action

    # Update target rating snapshot
    upsert_rating_for_pair(db, viewer_profile=viewer, candidate_profile=target)

    is_match = False
    if payload.action == "like":
        reverse_like = db.scalar(
            select(Interaction).where(
                Interaction.from_user_id == target.user_id,
                Interaction.to_profile_id == viewer.id,
                Interaction.action == "like",
            )
        )
        if reverse_like is not None:
            a, b = sorted([viewer.user_id, target.user_id], key=lambda x: str(x))
            m = db.scalar(select(Match).where(Match.user_a_id == a, Match.user_b_id == b))
            if m is None:
                db.add(Match(user_a_id=a, user_b_id=b))
            is_match = True

    db.commit()
    return InteractionOut(ok=True, is_match=is_match)


@app.post("/feed/action", response_model=FeedActionOut)
def feed_action(payload: FeedActionIn, db: Session = Depends(get_db)) -> FeedActionOut:
    """
    Convenience endpoint for the bot UI: record like/skip and return next feed card.
    This prevents the bot from needing to call two endpoints in sequence.
    """
    res = create_interaction(InteractionIn(**payload.model_dump()), db=db)
    try:
        nxt = feed_next(FeedNextIn(telegram_id=payload.telegram_id), db=db)
    except HTTPException as e:
        if e.status_code == 404:
            return FeedActionOut(ok=bool(res.ok), is_match=bool(res.is_match), next=None)
        raise
    return FeedActionOut(ok=bool(res.ok), is_match=bool(res.is_match), next=nxt)


@app.post("/dev/reset_user_state", response_model=DevResetUserStateOut)
def dev_reset_user_state(payload: DevResetUserStateIn, db: Session = Depends(get_db)) -> DevResetUserStateOut:
    """
    Dev helper: clear user's swipe history and cached feed.
    - deletes outgoing interactions (like/skip)
    - deletes matches involving the user
    - clears Redis feed list for this user
    """
    user = _get_user_by_telegram(db, payload.telegram_id)

    deleted_interactions = db.execute(delete(Interaction).where(Interaction.from_user_id == user.id)).rowcount or 0
    deleted_matches = (
        db.execute(delete(Match).where(or_(Match.user_a_id == user.id, Match.user_b_id == user.id))).rowcount or 0
    )
    db.commit()

    # Clear cached feed for this user (best-effort).
    try:
        r = _get_redis()
        r.delete(_feed_key(user.id))
        r.delete(_feed_meta_key(user.id))
    except Exception:
        pass

    return DevResetUserStateOut(
        ok=True,
        deleted_interactions=int(deleted_interactions),
        deleted_matches=int(deleted_matches),
    )
