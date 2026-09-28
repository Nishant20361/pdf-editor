"""Local disk storage backend implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.storage.base import StorageBackend
from app.utils.security import validate_path_safety

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage separating originals, previews, and exports."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or settings.UPLOAD_DIR
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create category subdirectories."""
        for category in ["originals", "previews", "exports"]:
            (self.root_dir / category).mkdir(parents=True, exist_ok=True)

    def _get_category_dir(self, category: str) -> Path:
        cat_dir = self.root_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        return cat_dir

    def save(self, category: str, filename: str, data: bytes) -> str:
        cat_dir = self._get_category_dir(category)
        file_path = cat_dir / filename
        validated = validate_path_safety(file_path)
        validated.parent.mkdir(parents=True, exist_ok=True)
        validated.write_bytes(data)
        logger.info("Saved file locally in %s/%s (%d bytes)", category, filename, len(data))
        return f"{category}/{filename}"

    def get_path(self, category: str, filename: str) -> Path:
        cat_dir = self._get_category_dir(category)
        file_path = cat_dir / filename
        return validate_path_safety(file_path)

    def read(self, category: str, filename: str) -> bytes:
        path = self.get_path(category, filename)
        if not path.exists():
            raise FileNotFoundError(f"File not found in {category}: {filename}")
        return path.read_bytes()

    def delete(self, category: str, filename: str) -> bool:
        path = self.get_path(category, filename)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, category: str, filename: str) -> bool:
        path = self.get_path(category, filename)
        return path.exists()

    def get_url(self, category: str, filename: str, expires_in: int = 3600) -> str:
        # For local dev, endpoints stream files directly through authorized routes
        return f"/api/storage/{category}/{filename}"
