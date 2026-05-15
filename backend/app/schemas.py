from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TelegramUserUpsertIn(BaseModel):
    telegram_id: int = Field(ge=1)
    username: Optional[str] = None
    first_name: Optional[str] = None
    language: Optional[str] = None


class TelegramUserUpsertOut(BaseModel):
    user_id: str
    is_new: bool
    has_profile: bool = False


class ProfileUpsertIn(BaseModel):
    telegram_id: int = Field(ge=1)
    age: Optional[int] = Field(default=None, ge=18, le=120)
    gender: Optional[Literal["male", "female", "other"]] = None
    city: Optional[str] = Field(default=None, max_length=128)
    interests: Optional[str] = Field(default=None, max_length=512)
    about: Optional[str] = Field(default=None, max_length=1024)

    pref_gender: Optional[Literal["male", "female", "other"]] = None
    pref_age_min: Optional[int] = Field(default=None, ge=18, le=120)
    pref_age_max: Optional[int] = Field(default=None, ge=18, le=120)
    pref_city: Optional[str] = Field(default=None, max_length=128)

    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _validate_age_range(self) -> "ProfileUpsertIn":
        if self.pref_age_min is not None and self.pref_age_max is not None:
            if self.pref_age_min > self.pref_age_max:
                raise ValueError("pref_age_min must be <= pref_age_max")
        return self


class ProfileOut(BaseModel):
    profile_id: str
    user_id: str
    is_active: bool

    age: Optional[int]
    gender: Optional[str]
    city: Optional[str]
    interests: Optional[str]
    about: Optional[str]

    pref_gender: Optional[str]
    pref_age_min: Optional[int]
    pref_age_max: Optional[int]
    pref_city: Optional[str]


class FeedNextIn(BaseModel):
    telegram_id: int = Field(ge=1)


class FeedProfileOut(BaseModel):
    profile_id: str
    user_id: str
    telegram_id: int
    age: Optional[int]
    gender: Optional[str]
    city: Optional[str]
    interests: Optional[str]
    about: Optional[str]
    combined_score: float


class FeedActionIn(BaseModel):
    telegram_id: int = Field(ge=1)
    to_profile_id: str
    action: Literal["like", "skip"]


class FeedActionOut(BaseModel):
    ok: bool
    is_match: bool = False
    next: Optional[FeedProfileOut] = None


class InteractionIn(BaseModel):
    telegram_id: int = Field(ge=1)
    to_profile_id: str
    action: Literal["like", "skip"]


class InteractionOut(BaseModel):
    ok: bool
    is_match: bool = False


class DevResetUserStateIn(BaseModel):
    telegram_id: int = Field(ge=1)


class DevResetUserStateOut(BaseModel):
    ok: bool
    deleted_interactions: int
    deleted_matches: int


class ProfilePhotoOut(BaseModel):
    photo_id: str
    url: str
    is_main: bool


class ReferralApplyIn(BaseModel):
    invitee_telegram_id: int = Field(ge=1)
    inviter_telegram_id: int = Field(ge=1)
