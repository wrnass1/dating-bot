from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    api_base_url: str = "http://api:8000"
    api_service_token: Optional[str] = None
    redis_url: str = "redis://redis:6379/0"
    enable_dev_endpoints: bool = False


settings = Settings()
