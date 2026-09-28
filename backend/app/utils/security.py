"""Security utilities — filename sanitization and path traversal prevention."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import settings


def generate_secure_filename(original_filename: str) -> str:
    """Generate a secure random filename preserving the original extension.

    Never trusts the uploaded filename — uses UUID4 for uniqueness.
    """
    ext = Path(original_filename).suffix.lower()
    # Only allow known-safe extensions
    safe_ext = ext if ext.lstrip(".") in settings.ALLOWED_EXTENSIONS else ""
    return f"{uuid.uuid4().hex}{safe_ext}"


def sanitize_filename(filename: str) -> str:
    """Strip directory components and dangerous characters from a filename."""
    # Take only the basename
    name = Path(filename).name
    # Remove any null bytes or path separators
    name = name.replace("\x00", "").replace("/", "").replace("\\", "")
    # Remove leading dots to prevent hidden files
    name = name.lstrip(".")
    # Remove non-ASCII and special characters
    name = re.sub(r"[^\w\-.]", "_", name)
    return name or "unnamed"


def validate_path_safety(file_path: Path, allowed_root: Path | None = None) -> Path:
    """Ensure a file path doesn't escape the upload directory.

    Prevents path traversal attacks (../../etc/passwd).

    Returns the resolved absolute path.
    Raises ValueError if the path would escape the allowed root.
    """
    root = (allowed_root or settings.UPLOAD_DIR).resolve()
    resolved = file_path.resolve()

    if not str(resolved).startswith(str(root)):
        raise ValueError(
            f"Path traversal detected: '{file_path}' resolves outside '{root}'"
        )
    return resolved


def generate_document_id() -> str:
    """Generate a unique document identifier."""
    return uuid.uuid4().hex
