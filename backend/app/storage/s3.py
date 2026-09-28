"""S3-compatible object storage backend."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend

logger = logging.getLogger(__name__)


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend (AWS S3, MinIO, Wasabi, Cloudflare R2).
    Falls back gracefully to local storage if boto3 or credentials are not configured.
    """

    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME
        self._s3_client = None
        self._local_fallback = LocalStorageBackend()

        if settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY_ID:
            try:
                import boto3
                self._s3_client = boto3.client(
                    "s3",
                    endpoint_url=settings.S3_ENDPOINT_URL or None,
                    aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                    region_name=settings.S3_REGION,
                )
                logger.info("Connected to S3 bucket: %s", self.bucket)
            except Exception as exc:
                logger.warning("Could not initialize S3 client (%s); falling back to local storage", exc)
                self._s3_client = None

    def save(self, category: str, filename: str, data: bytes) -> str:
        key = f"{category}/{filename}"
        if self._s3_client and self.bucket:
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                )
                return key
            except Exception as exc:
                logger.error("S3 upload failed for %s: %s; using local fallback", key, exc)

        return self._local_fallback.save(category, filename, data)

    def get_path(self, category: str, filename: str) -> Path:
        # S3 does not have local paths; fallback to cached/local file
        return self._local_fallback.get_path(category, filename)

    def read(self, category: str, filename: str) -> bytes:
        key = f"{category}/{filename}"
        if self._s3_client and self.bucket:
            try:
                resp = self._s3_client.get_object(Bucket=self.bucket, Key=key)
                return resp["Body"].read()
            except Exception as exc:
                logger.error("S3 download failed for %s: %s", key, exc)

        return self._local_fallback.read(category, filename)

    def delete(self, category: str, filename: str) -> bool:
        key = f"{category}/{filename}"
        s3_deleted = False
        if self._s3_client and self.bucket:
            try:
                self._s3_client.delete_object(Bucket=self.bucket, Key=key)
                s3_deleted = True
            except Exception as exc:
                logger.error("S3 delete failed for %s: %s", key, exc)

        local_deleted = self._local_fallback.delete(category, filename)
        return s3_deleted or local_deleted

    def exists(self, category: str, filename: str) -> bool:
        key = f"{category}/{filename}"
        if self._s3_client and self.bucket:
            try:
                self._s3_client.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                pass
        return self._local_fallback.exists(category, filename)

    def get_url(self, category: str, filename: str, expires_in: int = 3600) -> str:
        key = f"{category}/{filename}"
        if self._s3_client and self.bucket:
            try:
                url = self._s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
                return url
            except Exception as exc:
                logger.warning("Failed to generate S3 presigned URL: %s", exc)

        return self._local_fallback.get_url(category, filename, expires_in)
