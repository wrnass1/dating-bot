from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_service_token: Optional[str] = None
    enable_dev_endpoints: bool = False
    feed_batch_size: int = 10
    feed_cache_ttl_seconds: int = 900


settings = Settings()
