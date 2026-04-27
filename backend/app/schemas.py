from pydantic import BaseModel, Field


class TelegramUserUpsertIn(BaseModel):
    telegram_id: int = Field(ge=1)
    username: str | None = None
    first_name: str | None = None
    language: str | None = None


class TelegramUserUpsertOut(BaseModel):
    user_id: str
    is_new: bool


class ProfileUpsertIn(BaseModel):
    telegram_id: int = Field(ge=1)
    age: int | None = Field(default=None, ge=18, le=120)
    gender: str | None = None
    city: str | None = None
    interests: str | None = None
    about: str | None = None

    pref_gender: str | None = None
    pref_age_min: int | None = Field(default=None, ge=18, le=120)
    pref_age_max: int | None = Field(default=None, ge=18, le=120)
    pref_city: str | None = None

    is_active: bool | None = None


class ProfileOut(BaseModel):
    profile_id: str
    user_id: str
    is_active: bool

    age: int | None
    gender: str | None
    city: str | None
    interests: str | None
    about: str | None

    pref_gender: str | None
    pref_age_min: int | None
    pref_age_max: int | None
    pref_city: str | None


class FeedNextIn(BaseModel):
    telegram_id: int = Field(ge=1)


class FeedProfileOut(BaseModel):
    profile_id: str
    user_id: str
    telegram_id: int
    age: int | None
    gender: str | None
    city: str | None
    interests: str | None
    about: str | None
    combined_score: float


class FeedActionIn(BaseModel):
    telegram_id: int = Field(ge=1)
    to_profile_id: str
    action: str  # "like" | "skip"


class FeedActionOut(BaseModel):
    ok: bool
    is_match: bool = False
    next: FeedProfileOut | None = None


class InteractionIn(BaseModel):
    telegram_id: int = Field(ge=1)
    to_profile_id: str
    action: str  # "like" | "skip"


class InteractionOut(BaseModel):
    ok: bool
    is_match: bool = False


class DevResetUserStateIn(BaseModel):
    telegram_id: int = Field(ge=1)


class DevResetUserStateOut(BaseModel):
    ok: bool
    deleted_interactions: int
    deleted_matches: int

