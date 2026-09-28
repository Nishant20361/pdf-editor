"""Storage module factory."""

from app.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.s3 import S3StorageBackend

_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Get singleton storage backend based on configuration."""
    global _storage_instance
    if _storage_instance is None:
        if settings.STORAGE_BACKEND.lower() == "s3" and settings.S3_BUCKET_NAME:
            _storage_instance = S3StorageBackend()
        else:
            _storage_instance = LocalStorageBackend()
    return _storage_instance
