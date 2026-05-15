from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_events_queue: str = "dating.events"

    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio12345"
    s3_bucket: str = "dating-photos"
    # Used by the bot to download images from inside Docker network.
    # Telegram servers can't reach your localhost, so don't use "localhost" here.
    s3_public_base_url: str = "http://minio:9000/dating-photos"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_service_token: Optional[str] = None
    enable_dev_endpoints: bool = False
    feed_batch_size: int = 10
    feed_cache_ttl_seconds: int = 900
    enable_mq_publish: bool = True


settings = Settings()
