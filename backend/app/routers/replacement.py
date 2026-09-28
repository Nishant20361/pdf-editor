"""Replacement/edit router — CRUD for edits, preview rendering, undo/redo."""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth.dependencies import get_current_user_or_default
from app.config import settings
from app.db.models import User
from app.models.document import DocumentType, document_store
from app.models.edit import (
    CreateEditRequest,
    EditRecord,
    EditStore,
    UpdateEditRequest,
    edit_store,
)
from app.services.file_service import get_file_path
from app.services.image_service import get_original_image_bytes
from app.services.replacement_service import apply_edits_to_image
from app.services.pdf_replacement_service import render_single_page_preview

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["replacement"])

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_doc(doc_id: str, user: Optional[User] = None):
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": "Document not found.", "error_code": "NOT_FOUND"})
    if user and doc.user_id and doc.user_id != user.id:
        raise HTTPException(status_code=403, detail={"error": "Access forbidden: you do not own this document.", "error_code": "FORBIDDEN"})
    return doc


def _sanitize_text(text: str) -> str:
    """Basic sanitization — strip control chars, limit length."""
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32))
    return cleaned[:2000]


# ---- CRUD ----

@router.post("/documents/{doc_id}/edits", status_code=201)
async def create_edit(
    doc_id: str,
    req: CreateEditRequest,
    user: User = Depends(get_current_user_or_default),
):
    doc = _validate_doc(doc_id, user)
    if req.page_number >= doc.page_count:
        raise HTTPException(status_code=400, detail={"error": "Page out of range.", "error_code": "PAGE_OUT_OF_RANGE"})

    edit = EditRecord(
        document_id=doc_id,
        page_number=req.page_number,
        original_text=_sanitize_text(req.original_text),
        replacement_text=_sanitize_text(req.replacement_text),
        original_box=req.original_box,
        current_box=req.current_box or req.original_box,
        detection_source=req.detection_source,
        ocr_confidence=req.ocr_confidence,
        font_family=req.font_family,
        font_size=req.font_size,
        font_color=req.font_color,
        font_weight=req.font_weight,
        font_style=req.font_style,
        rotation=req.rotation,
        alignment=req.alignment,
        letter_spacing=req.letter_spacing,
        line_height=req.line_height,
        bg_cleanup=req.bg_cleanup,
        bg_color=req.bg_color,
    )
    edit_store.add(edit)
    return edit.model_dump(mode="json")


@router.get("/documents/{doc_id}/edits")
async def list_edits(
    doc_id: str,
    page: int | None = Query(default=None, ge=0),
    user: User = Depends(get_current_user_or_default),
):
    _validate_doc(doc_id, user)
    edits = edit_store.list_edits(doc_id, page=page)
    return {
        "edits": [e.model_dump(mode="json") for e in edits],
        "count": len(edits),
    }


@router.get("/documents/{doc_id}/edits/{edit_id}")
async def get_edit(
    doc_id: str,
    edit_id: str,
    user: User = Depends(get_current_user_or_default),
):
    _validate_doc(doc_id, user)
    edit = edit_store.get(doc_id, edit_id)
    if edit is None:
        raise HTTPException(status_code=404, detail={"error": "Edit not found.", "error_code": "NOT_FOUND"})
    return edit.model_dump(mode="json")


@router.patch("/documents/{doc_id}/edits/{edit_id}")
async def update_edit(
    doc_id: str,
    edit_id: str,
    req: UpdateEditRequest,
    user: User = Depends(get_current_user_or_default),
):
    _validate_doc(doc_id, user)
    # Sanitize replacement text if provided
    if req.replacement_text is not None:
        req.replacement_text = _sanitize_text(req.replacement_text)
    edit = edit_store.update(doc_id, edit_id, req)
    if edit is None:
        raise HTTPException(status_code=404, detail={"error": "Edit not found.", "error_code": "NOT_FOUND"})
    return edit.model_dump(mode="json")


@router.delete("/documents/{doc_id}/edits/{edit_id}")
async def delete_edit(
    doc_id: str,
    edit_id: str,
    user: User = Depends(get_current_user_or_default),
):
    _validate_doc(doc_id, user)
    deleted = edit_store.delete(doc_id, edit_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": "Edit not found.", "error_code": "NOT_FOUND"})
    return {"message": "Edit deleted.", "id": edit_id}


# ---- Undo / Redo / Reset ----

@router.post("/documents/{doc_id}/edits/undo")
async def undo_edits(doc_id: str, user: User = Depends(get_current_user_or_default)):
    _validate_doc(doc_id, user)
    success = edit_store.undo(doc_id)
    edits = edit_store.list_edits(doc_id)
    return {"success": success, "edits": [e.model_dump(mode="json") for e in edits]}


@router.post("/documents/{doc_id}/edits/redo")
async def redo_edits(doc_id: str, user: User = Depends(get_current_user_or_default)):
    _validate_doc(doc_id, user)
    success = edit_store.redo(doc_id)
    edits = edit_store.list_edits(doc_id)
    return {"success": success, "edits": [e.model_dump(mode="json") for e in edits]}


@router.post("/documents/{doc_id}/edits/reset-page/{page_number}")
async def reset_page_edits(
    doc_id: str,
    page_number: int,
    user: User = Depends(get_current_user_or_default),
):
    _validate_doc(doc_id, user)
    count = edit_store.reset_page(doc_id, page_number)
    return {"removed": count}


@router.post("/documents/{doc_id}/edits/reset")
async def reset_document_edits(doc_id: str, user: User = Depends(get_current_user_or_default)):
    _validate_doc(doc_id, user)
    count = edit_store.reset_document(doc_id)
    return {"removed": count}


# ---- Preview with Edits Applied ----

@router.get("/documents/{doc_id}/preview-with-edits")
@router.get("/documents/{doc_id}/preview-edits")
async def get_preview_with_edits(
    doc_id: str,
    page: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user_or_default),
):
    """Render a preview image with all active edits applied."""
    doc = _validate_doc(doc_id, user)
    if page >= doc.page_count:
        raise HTTPException(status_code=400, detail={"error": "Page out of range.", "error_code": "PAGE_OUT_OF_RANGE"})

    try:
        file_path = get_file_path(doc)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "File not found.", "error_code": "FILE_MISSING"})

    edits = edit_store.list_edits(doc_id, page=page)

    if doc.document_type == DocumentType.IMAGE:
        # If no edits, return original
        if not edits:
            orig = get_original_image_bytes(file_path)
            return Response(content=orig, media_type=doc.mime_type, headers={"Cache-Control": "no-cache"})

        rendered = apply_edits_to_image(file_path.read_bytes(), edits)
        return Response(content=rendered, media_type="image/png", headers={"Cache-Control": "no-cache"})

    elif doc.document_type == DocumentType.PDF:
        rendered = render_single_page_preview(
            file_path=file_path,
            page_number=page,
            edits=edits,
            content_type="native",
            dpi=settings.PREVIEW_DPI,
        )
        return Response(content=rendered, media_type="image/png", headers={"Cache-Control": "no-cache"})

    raise HTTPException(status_code=400, detail={"error": "Unsupported document type.", "error_code": "UNSUPPORTED_TYPE"})
