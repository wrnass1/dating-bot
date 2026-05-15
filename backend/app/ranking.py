from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Interaction, Match, Profile, ProfilePhoto, Rating, Referral


WEIGHTS = {
    "primary": 0.55,
    "behavioral": 0.30,
    "referral": 0.10,
    "recency": 0.05,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _field_filled(value: Optional[object]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _interest_tokens(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def count_profile_photos(db: Session, profile_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count()).select_from(ProfilePhoto).where(ProfilePhoto.profile_id == profile_id)) or 0
    )


def compute_profile_quality_score(candidate: Profile, *, photo_count: int = 0) -> float:
    """
    Level 1: profile completeness and uploaded photos.
    """
    fields = [
        candidate.age,
        candidate.gender,
        candidate.city,
        candidate.interests,
        candidate.about,
        candidate.pref_gender,
        candidate.pref_age_min,
        candidate.pref_age_max,
        candidate.pref_city,
    ]
    filled = sum(1 for f in fields if _field_filled(f))
    completeness = filled / len(fields)
    score = 90.0 * completeness
    score += _clamp(10.0 * math.log1p(max(photo_count, 0)), 0.0, 10.0)
    return _clamp(score, 0.0, 100.0)


def compute_preference_score(viewer: Profile, candidate: Profile) -> float:
    """
    Level 1: viewer preferences (gender, city, age) and shared interests.
    """
    score = 0.0
    if viewer.pref_gender and candidate.gender and viewer.pref_gender == candidate.gender:
        score += 30.0
    if viewer.pref_city and candidate.city and viewer.pref_city.lower() == candidate.city.lower():
        score += 25.0
    if candidate.age is not None and viewer.pref_age_min is not None and viewer.pref_age_max is not None:
        if viewer.pref_age_min <= candidate.age <= viewer.pref_age_max:
            score += 25.0

    shared = _interest_tokens(viewer.interests) & _interest_tokens(candidate.interests)
    if shared:
        score += _clamp(20.0 * len(shared), 0.0, 20.0)

    return _clamp(score, 0.0, 100.0)


def compute_behavioral_score(db: Session, profile_id: uuid.UUID, user_id: uuid.UUID) -> float:
    """
    Level 2: likes, conversion, mutual matches, recent activity window.
    """
    likes = int(
        db.scalar(
            select(func.count()).select_from(Interaction).where(
                Interaction.to_profile_id == profile_id, Interaction.action == "like"
            )
        )
        or 0
    )
    skips = int(
        db.scalar(
            select(func.count()).select_from(Interaction).where(
                Interaction.to_profile_id == profile_id, Interaction.action == "skip"
            )
        )
        or 0
    )
    total = likes + skips
    if total == 0:
        conversion_part = 0.0
    else:
        conversion_part = 70.0 * (likes / total)

    match_count = int(
        db.scalar(
            select(func.count()).select_from(Match).where(
                or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
            )
        )
        or 0
    )
    match_part = _clamp(15.0 * math.log1p(match_count), 0.0, 25.0)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent = int(
        db.scalar(
            select(func.count()).select_from(Interaction).where(
                Interaction.to_profile_id == profile_id,
                Interaction.created_at >= week_ago,
            )
        )
        or 0
    )
    recency_part = _clamp(5.0 * math.log1p(recent), 0.0, 15.0)

    volume_bonus = _clamp(10.0 * math.log1p(total), 0.0, 20.0)
    score = conversion_part + match_part + recency_part + volume_bonus
    return _clamp(score, 0.0, 100.0)


def compute_referral_score(db: Session, user_id: uuid.UUID) -> float:
    """Level 3: bonus for users who invited others."""
    invited = int(
        db.scalar(select(func.count()).select_from(Referral).where(Referral.inviter_id == user_id)) or 0
    )
    return _clamp(20.0 * math.log1p(invited), 0.0, 100.0)


def compute_recency_activity_score(db: Session, profile_id: uuid.UUID) -> float:
    """Level 3: bonus for profiles with fresh engagement."""
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    recent = int(
        db.scalar(
            select(func.count()).select_from(Interaction).where(
                Interaction.to_profile_id == profile_id,
                Interaction.created_at >= day_ago,
            )
        )
        or 0
    )
    return _clamp(25.0 * math.log1p(recent), 0.0, 100.0)


def compute_combined_score(
    primary: float,
    behavioral: float,
    *,
    referral: float = 0.0,
    recency: float = 0.0,
) -> float:
    """Level 3: weighted model documented in WEIGHTS."""
    score = (
        WEIGHTS["primary"] * primary
        + WEIGHTS["behavioral"] * behavioral
        + WEIGHTS["referral"] * referral
        + WEIGHTS["recency"] * recency
    )
    return _clamp(score, 0.0, 100.0)


def compute_feed_score(viewer: Profile, candidate: Profile, rating: Optional[Rating]) -> float:
    global_score = float(rating.combined_score) if rating is not None else compute_profile_quality_score(candidate)
    preference_score = compute_preference_score(viewer, candidate)
    return _clamp(0.55 * preference_score + 0.45 * global_score, 0.0, 100.0)


def upsert_rating_snapshot(db: Session, *, candidate_profile: Profile) -> Rating:
    photo_count = count_profile_photos(db, candidate_profile.id)
    primary = compute_profile_quality_score(candidate_profile, photo_count=photo_count)
    behavioral = compute_behavioral_score(db, candidate_profile.id, candidate_profile.user_id)
    referral = compute_referral_score(db, candidate_profile.user_id)
    recency = compute_recency_activity_score(db, candidate_profile.id)
    combined = compute_combined_score(primary, behavioral, referral=referral, recency=recency)

    rating = db.scalar(select(Rating).where(Rating.profile_id == candidate_profile.id))
    if rating is None:
        rating = Rating(
            profile_id=candidate_profile.id,
            primary_score=primary,
            behavioral_score=behavioral,
            combined_score=combined,
        )
        db.add(rating)
    else:
        rating.primary_score = primary
        rating.behavioral_score = behavioral
        rating.combined_score = combined
    return rating


def upsert_rating_for_pair(db: Session, *, viewer_profile: Profile, candidate_profile: Profile) -> Rating:
    return upsert_rating_snapshot(db, candidate_profile=candidate_profile)
