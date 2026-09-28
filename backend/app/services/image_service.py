"""Image processing service — metadata extraction and preview generation."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from app.models.document import DocumentMetadata, document_store

logger = logging.getLogger(__name__)


def get_image_metadata(file_path: Path) -> dict:
    """Extract image dimensions and format information.

    Returns a dict with width, height, and format.
    """
    with Image.open(file_path) as img:
        return {
            "width": img.width,
            "height": img.height,
            "format": img.format or "UNKNOWN",
            "mode": img.mode,
        }


def update_image_metadata(doc: DocumentMetadata, file_path: Path) -> DocumentMetadata:
    """Update document metadata with image-specific information."""
    info = get_image_metadata(file_path)
    doc.width = info["width"]
    doc.height = info["height"]
    # Update in store
    document_store.add(doc)
    return doc


def generate_image_preview(file_path: Path, max_width: int = 1200, max_height: int = 1200) -> bytes:
    """Generate a preview image, resizing if necessary.

    Returns PNG bytes of the preview image.
    """
    with Image.open(file_path) as img:
        # Convert to RGB if necessary (handles RGBA, CMYK, etc.)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Resize if the image exceeds preview dimensions
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.LANCZOS)

        # Save as PNG for sharp preview
        from io import BytesIO

        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def get_original_image_bytes(file_path: Path) -> bytes:
    """Read the original image file bytes."""
    return file_path.read_bytes()
