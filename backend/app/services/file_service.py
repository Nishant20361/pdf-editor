"""File service — save, retrieve, and delete uploaded files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import settings
from app.models.document import DocumentMetadata, DocumentType, document_store
from app.utils.security import generate_document_id, generate_secure_filename, validate_path_safety
from app.utils.validation import (
    ValidationError,
    get_mime_from_extension,
    validate_file_extension,
    validate_file_size,
    validate_magic_bytes,
    validate_mime_type,
)

logger = logging.getLogger(__name__)


def ensure_upload_dir() -> Path:
    """Create the upload directory if it doesn't exist."""
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return settings.UPLOAD_DIR


def ensure_preview_dir(doc_id: str) -> Path:
    """Create a preview directory for a specific document."""
    preview_dir = settings.UPLOAD_DIR / "previews" / doc_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir


async def save_upload(
    file_data: bytes,
    original_filename: str,
    content_type: str | None = None,
    user_id: str | None = None,
) -> DocumentMetadata:
    """Validate and save an uploaded file.

    Returns DocumentMetadata on success.
    Raises ValidationError on failure.
    """
    # 1. Validate extension
    ext = validate_file_extension(original_filename)

    # 2. Validate size
    validate_file_size(len(file_data))

    # 3. Determine expected MIME type
    expected_mime = get_mime_from_extension(ext)

    # 4. Validate Content-Type header
    validate_mime_type(content_type, expected_mime)

    # 5. Validate magic bytes (file signature)
    validate_magic_bytes(file_data, expected_mime)

    # 6. Generate secure filename and document ID
    doc_id = generate_document_id()
    secure_name = generate_secure_filename(original_filename)

    # 7. Save to disk
    upload_dir = ensure_upload_dir()
    file_path = upload_dir / secure_name
    validated_path = validate_path_safety(file_path)

    validated_path.write_bytes(file_data)
    logger.info("Saved upload: %s -> %s (%d bytes)", original_filename, secure_name, len(file_data))

    # 8. Determine document type
    doc_type = DocumentType.PDF if ext == "pdf" else DocumentType.IMAGE

    # 9. Create metadata (image/PDF-specific metadata added by their services)
    metadata = DocumentMetadata(
        id=doc_id,
        user_id=user_id,
        original_filename=original_filename,
        stored_filename=secure_name,
        mime_type=expected_mime,
        file_size=len(file_data),
        document_type=doc_type,
    )

    # 10. Store metadata
    document_store.add(metadata)

    return metadata


def get_file_path(doc: DocumentMetadata) -> Path:
    """Get the validated file path for a document."""
    file_path = settings.UPLOAD_DIR / doc.stored_filename
    validated = validate_path_safety(file_path)
    if not validated.exists():
        raise FileNotFoundError(f"File not found: {doc.stored_filename}")
    return validated


def delete_document(doc_id: str) -> bool:
    """Delete a document and all associated files (original + previews + edits)."""
    doc = document_store.get(doc_id)
    if doc is None:
        return False

    # Delete the original file
    try:
        file_path = settings.UPLOAD_DIR / doc.stored_filename
        if file_path.exists():
            file_path.unlink()
    except OSError as exc:
        logger.warning("Failed to delete file for doc %s: %s", doc_id, exc)

    # Delete preview directory
    preview_dir = settings.UPLOAD_DIR / "previews" / doc_id
    if preview_dir.exists():
        shutil.rmtree(preview_dir, ignore_errors=True)

    # Clean up edits
    try:
        from app.models.edit import edit_store
        edit_store.clear_document(doc_id)
    except Exception as exc:
        logger.warning("Failed to clear edits for doc %s: %s", doc_id, exc)

    # Remove from store
    document_store.delete(doc_id)
    logger.info("Deleted document: %s", doc_id)
    return True
