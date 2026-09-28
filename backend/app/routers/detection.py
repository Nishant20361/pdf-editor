"""OCR and native-PDF text detection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user_or_default
from app.db.models import User
from app.models.detection import DetectionRequest, DetectionResponse
from app.models.document import document_store
from app.services.detection_service import detect_text
from app.services.file_service import get_file_path
from app.services.ocr_service import is_ocr_available

router = APIRouter(prefix="/api", tags=["detection"])


@router.post("/documents/{doc_id}/detect", response_model=DetectionResponse)
async def detect_document_text(
    doc_id: str,
    request: DetectionRequest,
    user: User = Depends(get_current_user_or_default),
) -> DetectionResponse:
    document = document_store.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail={"error": "Document not found.", "error_code": "NOT_FOUND"})
    if document.user_id and document.user_id != user.id:
        raise HTTPException(status_code=403, detail={"error": "Access forbidden: you do not own this document.", "error_code": "FORBIDDEN"})
    if request.page_number is not None and request.page_number >= document.page_count:
        raise HTTPException(status_code=400, detail={"error": "Page is out of range.", "error_code": "PAGE_OUT_OF_RANGE"})
    try:
        pages, detections, warnings = detect_text(
            document,
            get_file_path(document),
            request.query,
            request.case_sensitive,
            request.exact_match,
            request.page_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "error_code": "DETECTION_ERROR"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc), "error_code": "DETECTION_ERROR"})
    return DetectionResponse(
        document_id=doc_id,
        query=request.query,
        pages=pages,
        detections=detections,
        ocr_available=is_ocr_available(),
        warnings=warnings,
    )
