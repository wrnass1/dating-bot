from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("telegram_id", name="uq_users_telegram_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_profiles_user_id"),
        CheckConstraint("age >= 18 AND age <= 120", name="ck_profiles_age_range"),
        CheckConstraint("gender IS NULL OR gender IN ('male', 'female', 'other')", name="ck_profiles_gender"),
        CheckConstraint(
            "pref_gender IS NULL OR pref_gender IN ('male', 'female', 'other')",
            name="ck_profiles_pref_gender",
        ),
        CheckConstraint(
            "(pref_age_min IS NULL OR pref_age_min >= 18) AND (pref_age_max IS NULL OR pref_age_max <= 120)",
            name="ck_profiles_pref_age_range",
        ),
        CheckConstraint(
            "pref_age_min IS NULL OR pref_age_max IS NULL OR pref_age_min <= pref_age_max",
            name="ck_profiles_pref_age_order",
        ),
        Index("ix_profiles_active_city_gender_age", "is_active", "city", "gender", "age"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # "male" | "female" | "other"
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    interests: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # comma-separated for MVP
    about: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    pref_gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    pref_age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pref_age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pref_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(lazy="joined")
    ratings: Mapped["Rating"] = relationship(back_populates="profile", uselist=False)


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_profile_id", name="uq_interactions_from_to"),
        CheckConstraint("action IN ('like', 'skip')", name="ck_interactions_action"),
        Index("ix_interactions_to_action_created", "to_profile_id", "action", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    to_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # "like" | "skip"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_matches_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_a_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    user_b_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("profile_id", name="uq_ratings_profile_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False, index=True
    )

    primary_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    behavioral_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    profile: Mapped["Profile"] = relationship(back_populates="ratings")
