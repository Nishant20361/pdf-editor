"""Export data model — job state, request/response schemas."""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ExportFormat(str, Enum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    PDF = "pdf"
    PDF_FLATTENED = "pdf_flattened"
    ZIP_IMAGES = "zip_images"


class ExportMode(str, Enum):
    PRESERVE = "preserve"
    FLATTENED = "flattened"
    IMAGE_PAGES = "image_pages"
    COMPRESSED = "compressed"


class ExportStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PageSelection(str, Enum):
    ALL = "all"
    CURRENT = "current"
    EDITED = "edited"
    CUSTOM = "custom"


class ExportRequest(BaseModel):
    output_format: ExportFormat = ExportFormat.PDF
    mode: ExportMode = ExportMode.PRESERVE
    page_selection: PageSelection = PageSelection.ALL
    current_page: int = Field(default=0, ge=0)
    custom_pages: Optional[str] = Field(default=None, max_length=200)
    filename: Optional[str] = Field(default=None, max_length=200)
    quality: int = Field(default=85, ge=1, le=100)
    preserve_dimensions: bool = True
    output_width: Optional[int] = Field(default=None, ge=1, le=10000)
    output_height: Optional[int] = Field(default=None, ge=1, le=10000)
    flatten_edits: bool = True
    include_metadata: bool = True
    image_format_for_zip: str = Field(default="png", pattern=r"^(png|jpeg)$")

    @field_validator("custom_pages")
    @classmethod
    def validate_custom_pages(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not re.match(r"^[\d,\-\s]+$", v):
            raise ValueError("Invalid page range format. Use: 1-3,5,8-10")
        return v


class ExportJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str
    status: ExportStatus = ExportStatus.QUEUED
    output_format: ExportFormat = ExportFormat.PDF
    mode: ExportMode = ExportMode.PRESERVE
    filename: str = ""
    mime_type: str = ""
    file_size: int = 0
    page_count: int = 0
    progress: float = Field(default=0.0, ge=0, le=100)
    error: Optional[str] = None
    stored_filename: Optional[str] = None  # internal only, never exposed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    def to_response(self) -> dict:
        """Safe dict excluding internal paths."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "status": self.status.value,
            "output_format": self.output_format.value,
            "mode": self.mode.value,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def parse_page_range(spec: str, total_pages: int) -> list[int]:
    """Parse a page range string like '1-3,5,8-10' into a sorted list of 0-indexed page numbers."""
    pages: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                start = int(bounds[0])
                end = int(bounds[1])
            except ValueError:
                raise ValueError(f"Invalid range: '{part}'")
            if start < 1 or end < start or end > total_pages:
                raise ValueError(f"Range {start}-{end} is out of bounds (1-{total_pages})")
            for p in range(start, end + 1):
                pages.add(p - 1)
        else:
            try:
                p = int(part)
            except ValueError:
                raise ValueError(f"Invalid page number: '{part}'")
            if p < 1 or p > total_pages:
                raise ValueError(f"Page {p} is out of bounds (1-{total_pages})")
            pages.add(p - 1)
    return sorted(pages)


# ---- Persistent export store ----

class ExportStore:
    """Thread-safe per-document export store with database backing."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, ExportJob]] = {}  # doc_id -> {export_id -> job}
        self._lock = threading.Lock()

    def _sync_to_db(self, job: ExportJob) -> None:
        try:
            from app.db.database import SessionLocal
            from app.db.models import ExportJob as DbExportJob

            with SessionLocal() as db:
                db_job = db.query(DbExportJob).filter(DbExportJob.id == job.id).first()
                if not db_job:
                    db_job = DbExportJob(
                        id=job.id,
                        document_id=job.document_id,
                        output_format=job.output_format.value,
                        mode=job.mode.value,
                        filename=job.filename,
                        mime_type=job.mime_type,
                        file_size=job.file_size,
                        page_count=job.page_count,
                        progress=job.progress,
                        error=job.error,
                        status=job.status.value,
                        storage_path=job.storage_path,
                        created_at=job.created_at,
                        completed_at=job.completed_at,
                    )
                    db.add(db_job)
                else:
                    db_job.status = job.status.value
                    db_job.progress = job.progress
                    db_job.error = job.error
                    db_job.file_size = job.file_size
                    db_job.storage_path = job.storage_path
                    db_job.completed_at = job.completed_at
                db.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not sync export job to DB: %s", exc)

    def _load_from_db(self, doc_id: str) -> None:
        try:
            from app.db.database import SessionLocal
            from app.db.models import ExportJob as DbExportJob

            with SessionLocal() as db:
                db_jobs = db.query(DbExportJob).filter(DbExportJob.document_id == doc_id).all()
                if db_jobs:
                    self._jobs.setdefault(doc_id, {})
                    for dj in db_jobs:
                        job = ExportJob(
                            id=dj.id,
                            document_id=dj.document_id,
                            output_format=ExportFormat(dj.output_format),
                            mode=ExportMode(dj.mode),
                            filename=dj.filename,
                            mime_type=dj.mime_type,
                            file_size=dj.file_size,
                            page_count=dj.page_count,
                            progress=dj.progress,
                            error=dj.error,
                            status=ExportStatus(dj.status),
                            storage_path=dj.storage_path,
                            created_at=dj.created_at,
                            completed_at=dj.completed_at,
                        )
                        self._jobs[doc_id][job.id] = job
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not load export jobs from DB: %s", exc)

    def add(self, job: ExportJob) -> ExportJob:
        with self._lock:
            self._jobs.setdefault(job.document_id, {})[job.id] = job
        self._sync_to_db(job)
        return job

    def get(self, doc_id: str, export_id: str) -> Optional[ExportJob]:
        with self._lock:
            if doc_id not in self._jobs:
                self._load_from_db(doc_id)
            return self._jobs.get(doc_id, {}).get(export_id)

    def update(self, job: ExportJob) -> None:
        with self._lock:
            self._jobs.setdefault(job.document_id, {})[job.id] = job
        self._sync_to_db(job)

    def delete(self, doc_id: str, export_id: str) -> bool:
        with self._lock:
            if doc_id not in self._jobs:
                self._load_from_db(doc_id)
            jobs = self._jobs.get(doc_id, {})
            removed = jobs.pop(export_id, None) is not None
        try:
            from app.db.database import SessionLocal
            from app.db.models import ExportJob as DbExportJob

            with SessionLocal() as db:
                db.query(DbExportJob).filter(DbExportJob.id == export_id).delete(synchronize_session=False)
                db.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not delete export job from DB: %s", exc)
        return removed

    def list_exports(self, doc_id: str) -> list[ExportJob]:
        with self._lock:
            if doc_id not in self._jobs:
                self._load_from_db(doc_id)
            return list(self._jobs.get(doc_id, {}).values())


export_store = ExportStore()
