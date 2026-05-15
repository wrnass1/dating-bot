from __future__ import annotations

import uuid
from typing import Optional

from app.settings import settings

_client = None
_bucket_ready = False


def _get_client():
    global _client
    if _client is None:
        import boto3  # type: ignore

        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
    return _client


def ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    client = _get_client()
    buckets = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if settings.s3_bucket not in buckets:
        client.create_bucket(Bucket=settings.s3_bucket)
    _bucket_ready = True


def upload_profile_photo(*, profile_id: str, content: bytes, content_type: str) -> tuple[str, str]:
    ensure_bucket()
    key = f"profiles/{profile_id}/{uuid.uuid4().hex}.jpg"
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType=content_type or "image/jpeg",
        # For local demo: make objects publicly readable so Telegram/bot can download by URL.
        # Otherwise you'll get 403 Forbidden when sending photos.
        ACL="public-read",
    )
    url = f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    return key, url


def download_object(*, storage_key: str) -> bytes:
    """
    Download an object from S3/MinIO as bytes.
    Used as a proxy for the Telegram bot so we don't rely on public ACL.
    """
    client = _get_client()
    obj = client.get_object(Bucket=settings.s3_bucket, Key=storage_key)
    return obj["Body"].read()


def delete_object(storage_key: str) -> None:
    client = _get_client()
    client.delete_object(Bucket=settings.s3_bucket, Key=storage_key)


def is_storage_configured() -> bool:
    return bool(settings.s3_endpoint_url and settings.s3_bucket)
