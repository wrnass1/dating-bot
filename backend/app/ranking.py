from __future__ import annotations

import math
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Interaction, Profile, Rating


WEIGHTS = {
    "primary": 0.7,
    "behavioral": 0.3,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _field_filled(value: Optional[object]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def compute_profile_quality_score(candidate: Profile, photo_count: int = 0) -> float:
    """
    Global part of Level 1: profile completeness and media quality.
    It is safe to persist because it does not depend on a particular viewer.
    Score is normalized to [0, 100].
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

    # Photos count (MVP: accept as parameter)
    score += _clamp(10.0 * math.log1p(max(photo_count, 0)), 0.0, 10.0)

    return _clamp(score, 0.0, 100.0)


def compute_preference_score(viewer: Profile, candidate: Profile) -> float:
    """
    Viewer-specific matching score. This is intentionally not persisted in ratings,
    because two viewers can rank the same profile differently.
    """
    score = 0.0
    if viewer.pref_gender and candidate.gender and viewer.pref_gender == candidate.gender:
        score += 35.0
    if viewer.pref_city and candidate.city and viewer.pref_city.lower() == candidate.city.lower():
        score += 30.0
    if candidate.age is not None and viewer.pref_age_min is not None and viewer.pref_age_max is not None:
        if viewer.pref_age_min <= candidate.age <= viewer.pref_age_max:
            score += 35.0
    return _clamp(score, 0.0, 100.0)


def compute_behavioral_score(db: Session, profile_id: uuid.UUID) -> float:
    """
    Level 2: based on interactions with candidate profile.
    We compute from DB so it stays dynamic without background workers in stage 3.
    Normalized to [0, 100].
    """
    likes = db.scalar(
        select(func.count()).select_from(Interaction).where(
            Interaction.to_profile_id == profile_id, Interaction.action == "like"
        )
    )
    skips = db.scalar(
        select(func.count()).select_from(Interaction).where(
            Interaction.to_profile_id == profile_id, Interaction.action == "skip"
        )
    )
    likes = int(likes or 0)
    skips = int(skips or 0)
    total = likes + skips
    if total == 0:
        return 0.0

    conversion = likes / total  # [0..1]
    volume_bonus = _clamp(10.0 * math.log1p(total), 0.0, 30.0)
    score = 70.0 * conversion + volume_bonus
    return _clamp(score, 0.0, 100.0)


def compute_combined_score(primary: float, behavioral: float) -> float:
    """
    Level 3: weighted model.
    """
    score = WEIGHTS["primary"] * primary + WEIGHTS["behavioral"] * behavioral
    return _clamp(score, 0.0, 100.0)


def compute_feed_score(viewer: Profile, candidate: Profile, rating: Optional[Rating]) -> float:
    """
    Final score used for one viewer's feed: global profile quality/behavior plus
    viewer-specific preferences. Kept outside the ratings table to avoid stale,
    cross-user score pollution.
    """
    global_score = float(rating.combined_score) if rating is not None else compute_profile_quality_score(candidate)
    preference_score = compute_preference_score(viewer, candidate)
    return _clamp(0.55 * preference_score + 0.45 * global_score, 0.0, 100.0)


def upsert_rating_snapshot(db: Session, *, candidate_profile: Profile) -> Rating:
    primary = compute_profile_quality_score(candidate_profile)
    behavioral = compute_behavioral_score(db, candidate_profile.id)
    combined = compute_combined_score(primary, behavioral)

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
    """
    Backward-compatible wrapper. The persisted snapshot is intentionally global;
    viewer_profile is ignored to keep ratings stable across users.
    """
    return upsert_rating_snapshot(db, candidate_profile=candidate_profile)
