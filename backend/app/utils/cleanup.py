"""Automatic cleanup of expired temporary files."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from app.config import settings
from app.models.document import document_store

logger = logging.getLogger(__name__)


async def cleanup_expired_files() -> int:
    """Remove upload files and previews older than FILE_TTL_MINUTES.

    Returns the number of files removed.
    """
    upload_dir = settings.UPLOAD_DIR
    if not upload_dir.exists():
        return 0

    ttl_seconds = settings.FILE_TTL_MINUTES * 60
    now = time.time()
    removed = 0

    for path in upload_dir.rglob("*"):
        if not path.is_file():
            continue
        age = now - path.stat().st_mtime
        if age > ttl_seconds:
            try:
                # Find and remove the document store entry
                # The stored_filename is the file's name in the upload dir
                doc_id_to_remove = None
                for doc in document_store.list_all():
                    if doc.stored_filename == path.name:
                        doc_id_to_remove = doc.id
                        break

                path.unlink(missing_ok=True)
                removed += 1

                if doc_id_to_remove:
                    document_store.delete(doc_id_to_remove)

                logger.info("Cleaned up expired file: %s (age: %.0fs)", path.name, age)
            except OSError as exc:
                logger.warning("Failed to remove expired file %s: %s", path, exc)

    # Also clean preview directories for removed documents
    previews_dir = upload_dir / "previews"
    if previews_dir.exists():
        for preview_dir in previews_dir.iterdir():
            if preview_dir.is_dir():
                # Check if the associated document still exists
                doc_exists = any(
                    d.id == preview_dir.name for d in document_store.list_all()
                )
                if not doc_exists:
                    try:
                        for f in preview_dir.iterdir():
                            f.unlink(missing_ok=True)
                        preview_dir.rmdir()
                        removed += 1
                        logger.info("Cleaned up preview dir: %s", preview_dir.name)
                    except OSError as exc:
                        logger.warning("Failed to remove preview dir %s: %s", preview_dir, exc)

    if removed:
        logger.info("Cleanup completed: removed %d files/directories", removed)

    return removed


async def start_cleanup_task() -> asyncio.Task:
    """Start the periodic cleanup background task."""

    async def _loop() -> None:
        while True:
            try:
                await cleanup_expired_files()
            except Exception as exc:
                logger.error("Cleanup task error: %s", exc)
            await asyncio.sleep(settings.CLEANUP_INTERVAL_SECONDS)

    task = asyncio.create_task(_loop())
    logger.info(
        "Cleanup task started (interval: %ds, TTL: %dm)",
        settings.CLEANUP_INTERVAL_SECONDS,
        settings.FILE_TTL_MINUTES,
    )
    return task
