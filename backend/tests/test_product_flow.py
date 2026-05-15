from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Interaction, Profile, Rating, User


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def lpop(self, key: str) -> str | None:
        values = self.lists.get(key, [])
        if not values:
            return None
        return values.pop(0)

    def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)
            self.ttls.pop(key, None)

    def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    def ttl(self, key: str) -> int:
        if key in self.values or key in self.lists:
            return self.ttls.get(key, -1)
        return -2

    def scan_iter(self, match: str):
        yield from []


def make_client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fake_redis = FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main._get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.main.publish_event", lambda *args, **kwargs: None)

    client = TestClient(app)
    return client, TestingSessionLocal, fake_redis


def create_user_profile(client: TestClient, telegram_id: int, *, age: int, gender: str, city: str) -> str:
    client.post(
        "/users/telegram/upsert",
        json={"telegram_id": telegram_id, "username": f"u{telegram_id}", "first_name": "Test", "language": "ru"},
    ).raise_for_status()
    response = client.post(
        "/profiles/upsert",
        json={
            "telegram_id": telegram_id,
            "age": age,
            "gender": gender,
            "city": city,
            "interests": "music, sport",
            "about": "Short bio",
            "pref_gender": "female" if gender == "male" else "male",
            "pref_age_min": 18,
            "pref_age_max": 40,
            "pref_city": city,
        },
    )
    response.raise_for_status()
    return str(response.json()["profile_id"])


def test_feed_show_does_not_consume_card_until_action(monkeypatch):
    client, _, _ = make_client(monkeypatch)
    create_user_profile(client, 101, age=28, gender="male", city="Moscow")
    create_user_profile(client, 202, age=25, gender="female", city="Moscow")
    create_user_profile(client, 303, age=26, gender="female", city="Moscow")

    first = client.post("/feed/next", json={"telegram_id": 101}).json()
    second = client.post("/feed/next", json={"telegram_id": 101}).json()
    assert second["profile_id"] == first["profile_id"]

    after_action = client.post(
        "/feed/action",
        json={"telegram_id": 101, "to_profile_id": first["profile_id"], "action": "skip"},
    ).json()
    assert after_action["ok"] is True
    assert after_action["next"]["profile_id"] != first["profile_id"]


def test_mutual_like_creates_match_and_updates_behavioral_rating(monkeypatch):
    client, SessionLocal, _ = make_client(monkeypatch)
    profile_a = create_user_profile(client, 101, age=28, gender="male", city="Moscow")
    profile_b = create_user_profile(client, 202, age=25, gender="female", city="Moscow")

    first_like = client.post(
        "/interactions",
        json={"telegram_id": 101, "to_profile_id": profile_b, "action": "like"},
    ).json()
    assert first_like == {"ok": True, "is_match": False}

    second_like = client.post(
        "/interactions",
        json={"telegram_id": 202, "to_profile_id": profile_a, "action": "like"},
    ).json()
    assert second_like == {"ok": True, "is_match": True}

    db = SessionLocal()
    try:
        target = db.scalar(select(Profile).where(Profile.id == uuid.UUID(profile_b)))
        assert target is not None
        interaction_count = len(db.scalars(select(Interaction)).all())
        rating = db.scalar(select(Rating).where(Rating.profile_id == target.id))
        assert interaction_count == 2
        assert rating is not None
        assert rating.behavioral_score > 0
    finally:
        db.close()


def test_referral_increases_inviter_rating(monkeypatch):
    client, SessionLocal, _ = make_client(monkeypatch)
    create_user_profile(client, 301, age=27, gender="male", city="Moscow")
    create_user_profile(client, 302, age=24, gender="female", city="Moscow")

    client.post(
        "/referrals/apply",
        json={"inviter_telegram_id": 301, "invitee_telegram_id": 302},
    ).raise_for_status()

    db = SessionLocal()
    try:
        inviter_profile = db.scalar(select(Profile).join(User, User.id == Profile.user_id).where(User.telegram_id == 301))
        assert inviter_profile is not None
        rating = db.scalar(select(Rating).where(Rating.profile_id == inviter_profile.id))
        assert rating is not None
        assert rating.combined_score > 0
    finally:
        db.close()
