"""Abstract storage interface for file persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageBackend(ABC):
    """Abstract file storage backend."""

    @abstractmethod
    def save(self, category: str, filename: str, data: bytes) -> str:
        """Save file bytes into a category folder ('originals', 'previews', 'exports').
        Returns relative or storage path.
        """
        pass

    @abstractmethod
    def get_path(self, category: str, filename: str) -> Path:
        """Get local filesystem path to file."""
        pass

    @abstractmethod
    def read(self, category: str, filename: str) -> bytes:
        """Read file bytes."""
        pass

    @abstractmethod
    def delete(self, category: str, filename: str) -> bool:
        """Delete file."""
        pass

    @abstractmethod
    def exists(self, category: str, filename: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    def get_url(self, category: str, filename: str, expires_in: int = 3600) -> str:
        """Get access or signed download URL for file."""
        pass
