"""Export router — create, poll, download, and delete exports with ownership checks."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_or_default
from app.config import settings
from app.db.database import get_db
from app.db.models import ExportJob as DbExportJob, User
from app.models.document import document_store
from app.models.export import (
    ExportFormat,
    ExportJob,
    ExportRequest,
    ExportStatus,
    export_store,
)
from app.services.export_service import cleanup_export, get_export_file_path, run_export

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])


def _validate_doc(doc_id: str, user: Optional[User] = None):
    doc = document_store.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": "Document not found.", "error_code": "NOT_FOUND"})
    if user and doc.user_id and doc.user_id != user.id:
        raise HTTPException(status_code=403, detail={"error": "Access forbidden: you do not own this document.", "error_code": "FORBIDDEN"})
    return doc


def _validate_export(doc_id: str, export_id: str) -> ExportJob:
    job = export_store.get(doc_id, export_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "Export not found.", "error_code": "NOT_FOUND"})
    return job


@router.post("/documents/{doc_id}/exports", status_code=201)
async def create_export(
    doc_id: str,
    req: ExportRequest,
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Start an export job with user limits and ownership validation."""
    doc = _validate_doc(doc_id, user)

    # Check export limits
    if user.role != "test_user":
        user_exports = db.query(DbExportJob).filter(DbExportJob.user_id == user.id).count()
        if user_exports >= settings.MAX_EXPORTS_PER_HOUR * 5:  # generous total
            raise HTTPException(
                status_code=429,
                detail={"error": "Export limit reached. Please wait before creating more exports.", "error_code": "RATE_LIMIT_EXCEEDED"},
            )

    # Validate page range early
    if req.page_selection.value == "custom" and req.custom_pages:
        from app.models.export import parse_page_range
        try:
            parse_page_range(req.custom_pages, doc.page_count)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc), "error_code": "INVALID_PAGE_RANGE"})

    if req.page_selection.value == "current" and req.current_page >= doc.page_count:
        raise HTTPException(status_code=400, detail={"error": "Current page out of range.", "error_code": "PAGE_OUT_OF_RANGE"})

    job = ExportJob(document_id=doc_id, output_format=req.output_format, mode=req.mode)
    export_store.add(job)

    # Run export
    try:
        run_export(doc, job, req)
    except Exception as exc:
        logger.error("Export failed: %s", exc, exc_info=True)
        job.status = ExportStatus.FAILED
        job.error = "Internal export error."
        export_store.update(job)

    return job.to_response()


@router.get("/documents/{doc_id}/exports/{export_id}")
async def get_export_status(
    doc_id: str,
    export_id: str,
    user: User = Depends(get_current_user_or_default),
):
    """Poll export job status."""
    _validate_doc(doc_id, user)
    job = _validate_export(doc_id, export_id)
    return job.to_response()


@router.get("/documents/{doc_id}/exports/{export_id}/download")
async def download_export(
    doc_id: str,
    export_id: str,
    user: User = Depends(get_current_user_or_default),
):
    """Stream-download a completed export file."""
    _validate_doc(doc_id, user)
    job = _validate_export(doc_id, export_id)

    if job.status != ExportStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Export is {job.status.value}, not ready for download.", "error_code": "NOT_READY"},
        )

    path = get_export_file_path(job)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail={"error": "Export file not found.", "error_code": "FILE_MISSING"})

    def _stream():
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        _stream(),
        media_type=job.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{job.filename}"',
            "Content-Length": str(job.file_size),
        },
    )


@router.delete("/documents/{doc_id}/exports/{export_id}")
async def delete_export(
    doc_id: str,
    export_id: str,
    user: User = Depends(get_current_user_or_default),
):
    """Delete an export and its file."""
    _validate_doc(doc_id, user)
    job = _validate_export(doc_id, export_id)
    cleanup_export(job)
    export_store.delete(doc_id, export_id)
    return {"message": "Export deleted.", "id": export_id}
