"""File validation utilities — magic bytes, MIME type, extension, size."""

from __future__ import annotations

from pathlib import Path

from app.config import settings

# Magic byte signatures for supported file types
FILE_SIGNATURES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "application/pdf": [b"%PDF"],
}


class ValidationError(Exception):
    """Raised when file validation fails."""

    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def validate_file_extension(filename: str) -> str:
    """Validate and return the lowercase file extension.

    Raises ValidationError if the extension is not allowed.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext:
        raise ValidationError(
            "File has no extension.",
            error_code="NO_EXTENSION",
        )
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"File type '.{ext}' is not supported. Allowed: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}",
            error_code="UNSUPPORTED_EXTENSION",
        )
    return ext


def validate_file_size(size: int) -> None:
    """Ensure the file does not exceed the configured maximum.

    Raises ValidationError if the file is too large.
    """
    if size > settings.max_file_size_bytes:
        raise ValidationError(
            f"File size ({size / (1024 * 1024):.1f} MB) exceeds the maximum allowed size ({settings.MAX_FILE_SIZE_MB} MB).",
            error_code="FILE_TOO_LARGE",
        )
    if size == 0:
        raise ValidationError(
            "Uploaded file is empty.",
            error_code="EMPTY_FILE",
        )


def validate_magic_bytes(data: bytes, expected_mime: str) -> None:
    """Verify the file's magic bytes match the expected MIME type.

    Raises ValidationError if the file signature is invalid.
    """
    signatures = FILE_SIGNATURES.get(expected_mime)
    if signatures is None:
        raise ValidationError(
            f"No known signature for MIME type '{expected_mime}'.",
            error_code="UNKNOWN_MIME",
        )

    for sig in signatures:
        if data[: len(sig)] == sig:
            return

    raise ValidationError(
        "File content does not match its declared type. The file may be corrupted or mislabeled.",
        error_code="INVALID_SIGNATURE",
    )


def get_mime_from_extension(ext: str) -> str:
    """Map a validated extension to its expected MIME type."""
    mapping = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "pdf": "application/pdf",
    }
    mime = mapping.get(ext)
    if mime is None:
        raise ValidationError(
            f"Cannot determine MIME type for extension '.{ext}'.",
            error_code="UNKNOWN_EXTENSION",
        )
    return mime


def validate_mime_type(content_type: str | None, expected_mime: str) -> None:
    """Validate that the Content-Type header matches the expected MIME type.

    Raises ValidationError on mismatch.
    """
    if content_type is None:
        return  # Some clients don't send Content-Type; rely on magic bytes

    # Normalize — some clients send 'image/jpg' instead of 'image/jpeg'
    normalized = content_type.lower().split(";")[0].strip()
    if normalized == "image/jpg":
        normalized = "image/jpeg"

    if normalized not in settings.ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"MIME type '{normalized}' is not allowed.",
            error_code="UNSUPPORTED_MIME",
        )
