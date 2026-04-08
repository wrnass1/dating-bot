from pydantic import BaseModel, Field


class TelegramUserUpsertIn(BaseModel):
    telegram_id: int = Field(ge=1)
    username: str | None = None
    first_name: str | None = None
    language: str | None = None


class TelegramUserUpsertOut(BaseModel):
    user_id: str
    is_new: bool

