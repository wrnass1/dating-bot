import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Interaction, Profile, Rating


WEIGHTS = {
    "primary": 0.7,
    "behavioral": 0.3,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _field_filled(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def compute_primary_score(viewer: Profile, candidate: Profile, photo_count: int = 0) -> float:
    """
    Level 1: based on profile data + completeness + preference match.
    Score is normalized to [0, 100].
    """
    score = 0.0

    # Preferences match (viewer -> candidate)
    if viewer.pref_gender and candidate.gender and viewer.pref_gender == candidate.gender:
        score += 20.0
    if viewer.pref_city and candidate.city and viewer.pref_city.lower() == candidate.city.lower():
        score += 20.0
    if candidate.age is not None and viewer.pref_age_min is not None and viewer.pref_age_max is not None:
        if viewer.pref_age_min <= candidate.age <= viewer.pref_age_max:
            score += 20.0

    # Completeness (candidate)
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
    score += 30.0 * completeness

    # Photos count (MVP: accept as parameter)
    score += _clamp(10.0 * math.log1p(max(photo_count, 0)), 0.0, 10.0)

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


def upsert_rating_for_pair(db: Session, *, viewer_profile: Profile, candidate_profile: Profile) -> Rating:
    primary = compute_primary_score(viewer_profile, candidate_profile)
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

