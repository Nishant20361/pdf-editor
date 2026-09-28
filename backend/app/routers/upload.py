"""Upload and document management router — handles file upload with validation and user ownership."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_or_default
from app.config import settings
from app.db.database import get_db
from app.db.models import Document as DbDocument, User, AuditEvent
from app.models.document import DocumentType, document_store
from app.models.edit import edit_store
from app.models.export import export_store
from app.services.file_service import save_upload, get_file_path, delete_document
from app.services.image_service import update_image_metadata
from app.services.pdf_service import update_pdf_metadata, render_all_page_previews
from app.utils.validation import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Upload a file (image or PDF) for editing.

    Validates file type, size, and signature before saving.
    Enforces user storage limits and associates document with user.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail={
            "error": "No filename provided.",
            "error_code": "NO_FILENAME",
        })

    # Check user document count and storage limit for registered users
    if user.role != "test_user":
        user_docs = db.query(DbDocument).filter(DbDocument.user_id == user.id).all()
        if len(user_docs) >= settings.MAX_DOCUMENTS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail={"error": f"Maximum document limit ({settings.MAX_DOCUMENTS_PER_USER}) reached for this account.", "error_code": "DOC_LIMIT_REACHED"},
            )

        # Check total storage limit
        current_storage = sum(d.file_size for d in user_docs)
        if current_storage + (file.size or 0) > (settings.MAX_STORAGE_PER_USER_MB * 1024 * 1024):
            raise HTTPException(
                status_code=400,
                detail={"error": f"Storage quota exceeded ({settings.MAX_STORAGE_PER_USER_MB} MB limit).", "error_code": "STORAGE_LIMIT_EXCEEDED"},
            )

    try:
        # Read file data
        file_data = await file.read()

        # Save with full validation
        doc = await save_upload(
            file_data=file_data,
            original_filename=file.filename,
            content_type=file.content_type,
            user_id=user.id,
        )

        # Extract type-specific metadata
        file_path = get_file_path(doc)

        if doc.document_type == DocumentType.IMAGE:
            doc = update_image_metadata(doc, file_path)
            # Decompression bomb / pixel count check
            if doc.width and doc.height and (doc.width * doc.height > settings.MAX_IMAGE_PIXELS):
                delete_document(doc.id)
                raise HTTPException(
                    status_code=400,
                    detail={"error": "Image resolution exceeds maximum allowed limit (decompression bomb protection).", "error_code": "IMAGE_TOO_LARGE"},
                )
        elif doc.document_type == DocumentType.PDF:
            doc = update_pdf_metadata(doc, file_path)
            if doc.page_count > settings.MAX_PDF_PAGES:
                delete_document(doc.id)
                raise HTTPException(
                    status_code=400,
                    detail={"error": f"PDF exceeds maximum page limit ({settings.MAX_PDF_PAGES} pages).", "error_code": "PDF_TOO_MANY_PAGES"},
                )
            # Pre-render page previews
            render_all_page_previews(doc, file_path)

        logger.info(
            "Upload successful: doc_id=%s, type=%s, size=%d, user=%s",
            doc.id, doc.document_type.value, doc.file_size, user.id,
        )

        return JSONResponse(
            status_code=201,
            content={
                "id": doc.id,
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
                "document_type": doc.document_type.value,
                "width": doc.width,
                "height": doc.height,
                "page_count": doc.page_count,
                "created_at": doc.created_at.isoformat(),
            },
        )

    except HTTPException:
        raise
    except ValidationError as exc:
        logger.warning("Upload validation failed: %s", exc.message)
        raise HTTPException(
            status_code=422,
            detail={"error": exc.message, "error_code": exc.error_code},
        )
    except Exception as exc:
        logger.error("Upload failed: %s", exc, exist_ok=True if hasattr(exc, 'exist_ok') else False, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "An unexpected error occurred during upload.", "error_code": "INTERNAL_ERROR"},
        )


@router.get("/documents")
async def list_documents(
    search: Optional[str] = Query(None, description="Search by original filename"),
    sort_by: str = Query("date", description="Sort by 'date', 'name', or 'size'"),
    order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """List documents belonging to the authenticated user for the dashboard."""
    query = db.query(DbDocument).filter(DbDocument.user_id == user.id)

    if search:
        query = query.filter(DbDocument.original_filename.ilike(f"%{search.strip()}%"))

    if sort_by == "name":
        query = query.order_by(DbDocument.original_filename.asc() if order == "asc" else DbDocument.original_filename.desc())
    elif sort_by == "size":
        query = query.order_by(DbDocument.file_size.asc() if order == "asc" else DbDocument.file_size.desc())
    else:  # default date
        query = query.order_by(DbDocument.created_at.asc() if order == "asc" else DbDocument.created_at.desc())

    db_docs = query.all()

    items = []
    for d in db_docs:
        edits = edit_store.list_edits(d.id)
        exports = export_store.list_exports(d.id)
        latest_export = exports[-1] if exports else None

        items.append({
            "id": d.id,
            "original_filename": d.original_filename,
            "mime_type": d.mime_type,
            "file_size": d.file_size,
            "document_type": d.document_type,
            "width": d.width,
            "height": d.height,
            "page_count": d.page_count,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat() if d.updated_at else d.created_at.isoformat(),
            "edit_count": len(edits),
            "export_status": latest_export.status.value if latest_export else None,
            "latest_export_id": latest_export.id if latest_export else None,
        })

    return {"documents": items, "total": len(items)}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, user: User = Depends(get_current_user_or_default)):
    """Get metadata for an uploaded document with ownership enforcement."""
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Document not found.", "error_code": "NOT_FOUND"},
        )

    # Ownership check
    if doc.user_id and doc.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail={"error": "Access forbidden: you do not own this document.", "error_code": "FORBIDDEN"},
        )

    return {
        "id": doc.id,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "document_type": doc.document_type.value,
        "width": doc.width,
        "height": doc.height,
        "page_count": doc.page_count,
        "created_at": doc.created_at.isoformat(),
    }


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str, user: User = Depends(get_current_user_or_default)):
    """Delete a document and all associated files with ownership check."""
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

    deleted = delete_document(doc_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "Document not found.", "error_code": "NOT_FOUND"},
        )
    return {"message": "Document deleted successfully.", "id": doc_id}
