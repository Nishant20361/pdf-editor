"""Preview router — serves image and PDF page previews."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth.dependencies import get_current_user_or_default
from app.db.models import User
from app.models.document import DocumentType, document_store
from app.services.file_service import get_file_path
from app.services.image_service import generate_image_preview, get_original_image_bytes
from app.services.pdf_service import render_pdf_page, get_page_preview_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["preview"])


@router.get("/documents/{doc_id}/preview")
async def get_preview(
    doc_id: str,
    page: int = Query(default=0, ge=0, description="Page number (0-indexed, for PDFs)"),
    original: bool = Query(default=False, description="Return original resolution"),
    user: User = Depends(get_current_user_or_default),
):
    """Get a preview image for a document.

    For images: returns the image (resized for preview or original).
    For PDFs: returns the specified page rendered as PNG.
    """
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Document not found.", "error_code": "NOT_FOUND"},
        )

    if doc.user_id and doc.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail={"error": "Access forbidden: you do not own this document.", "error_code": "FORBIDDEN"},
        )

    try:
        file_path = get_file_path(doc)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "File no longer exists on server.", "error_code": "FILE_MISSING"},
        )

    try:
        if doc.document_type == DocumentType.IMAGE:
            if original:
                image_bytes = get_original_image_bytes(file_path)
                return Response(
                    content=image_bytes,
                    media_type=doc.mime_type,
                    headers={"Cache-Control": "public, max-age=3600"},
                )
            else:
                preview_bytes = generate_image_preview(file_path)
                return Response(
                    content=preview_bytes,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

        elif doc.document_type == DocumentType.PDF:
            if page >= doc.page_count:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Page {page} does not exist. PDF has {doc.page_count} pages (0-indexed).",
                        "error_code": "PAGE_OUT_OF_RANGE",
                    },
                )

            # Try cached preview first
            cached = get_page_preview_path(doc_id, page)
            if cached:
                return Response(
                    content=cached.read_bytes(),
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

            # Render on the fly
            page_bytes = render_pdf_page(file_path, page)
            return Response(
                content=page_bytes,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "error_code": "RENDER_ERROR"})
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as exc:
        logger.error("Preview generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to generate preview.", "error_code": "PREVIEW_ERROR"},
        )
