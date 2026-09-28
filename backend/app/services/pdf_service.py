"""PDF processing service — page rendering and metadata extraction."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF

from app.config import settings
from app.models.document import DocumentMetadata, document_store
from app.services.file_service import ensure_preview_dir

logger = logging.getLogger(__name__)


def get_pdf_metadata(file_path: Path) -> dict:
    """Extract PDF metadata: page count, dimensions of first page.

    Returns a dict with page_count, width, height.
    """
    doc = fitz.open(str(file_path))
    try:
        page_count = doc.page_count
        if page_count > 0:
            first_page = doc[0]
            rect = first_page.rect
            width = int(rect.width)
            height = int(rect.height)
        else:
            width = 0
            height = 0

        return {
            "page_count": page_count,
            "width": width,
            "height": height,
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
        }
    finally:
        doc.close()


def update_pdf_metadata(doc_meta: DocumentMetadata, file_path: Path) -> DocumentMetadata:
    """Update document metadata with PDF-specific information."""
    info = get_pdf_metadata(file_path)
    doc_meta.page_count = info["page_count"]
    doc_meta.width = info["width"]
    doc_meta.height = info["height"]
    # Update in store
    document_store.add(doc_meta)
    return doc_meta


def render_pdf_page(
    file_path: Path,
    page_number: int,
    dpi: int | None = None,
) -> bytes:
    """Render a single PDF page as a PNG image.

    Args:
        file_path: Path to the PDF file.
        page_number: 0-indexed page number.
        dpi: Resolution for rendering (default: settings.PREVIEW_DPI).

    Returns:
        PNG image bytes.

    Raises:
        ValueError: If page_number is out of range.
    """
    render_dpi = dpi or settings.PREVIEW_DPI
    zoom = render_dpi / 72  # PyMuPDF uses 72 DPI as base

    doc = fitz.open(str(file_path))
    try:
        if page_number < 0 or page_number >= doc.page_count:
            raise ValueError(
                f"Page {page_number} is out of range. PDF has {doc.page_count} pages."
            )

        page = doc[page_number]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        return pix.tobytes("png")
    finally:
        doc.close()


def render_all_page_previews(
    doc_meta: DocumentMetadata,
    file_path: Path,
    dpi: int | None = None,
) -> list[Path]:
    """Render all pages of a PDF as preview images.

    Saves PNG files to the preview directory.
    Returns list of preview file paths.
    """
    preview_dir = ensure_preview_dir(doc_meta.id)
    render_dpi = dpi or settings.PREVIEW_DPI
    zoom = render_dpi / 72

    doc = fitz.open(str(file_path))
    preview_paths = []

    try:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            preview_path = preview_dir / f"page_{page_num}.png"
            pix.save(str(preview_path))
            preview_paths.append(preview_path)

            logger.debug(
                "Rendered page %d/%d of doc %s",
                page_num + 1,
                doc.page_count,
                doc_meta.id,
            )
    finally:
        doc.close()

    logger.info(
        "Rendered %d pages for doc %s at %d DPI",
        len(preview_paths),
        doc_meta.id,
        render_dpi,
    )
    return preview_paths


def get_page_preview_path(doc_id: str, page_number: int) -> Path | None:
    """Get the cached preview path for a specific page."""
    preview_path = settings.UPLOAD_DIR / "previews" / doc_id / f"page_{page_number}.png"
    return preview_path if preview_path.exists() else None
