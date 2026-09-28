"""Document metadata model with persistent database backing."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    IMAGE = "image"
    PDF = "pdf"


class DocumentMetadata(BaseModel):
    """Metadata about an uploaded document."""

    id: str
    user_id: Optional[str] = None
    original_filename: str
    stored_filename: str
    mime_type: str
    file_size: int
    document_type: DocumentType
    width: Optional[int] = None
    height: Optional[int] = None
    page_count: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DocumentStore:
    """Thread-safe document store with persistent database backing."""

    def __init__(self) -> None:
        self._documents: dict[str, DocumentMetadata] = {}
        self._lock = threading.Lock()

    def _sync_to_db(self, doc: DocumentMetadata) -> None:
        """Persist document metadata to the database."""
        try:
            from app.db.database import SessionLocal
            from app.db.models import Document as DbDocument

            with SessionLocal() as db:
                db_doc = db.query(DbDocument).filter(DbDocument.id == doc.id).first()
                if not db_doc:
                    db_doc = DbDocument(
                        id=doc.id,
                        user_id=doc.user_id,
                        original_filename=doc.original_filename,
                        stored_filename=doc.stored_filename,
                        mime_type=doc.mime_type,
                        file_size=doc.file_size,
                        document_type=doc.document_type.value,
                        width=doc.width,
                        height=doc.height,
                        page_count=doc.page_count,
                        created_at=doc.created_at,
                    )
                    db.add(db_doc)
                else:
                    db_doc.user_id = doc.user_id or db_doc.user_id
                    db_doc.original_filename = doc.original_filename
                    db_doc.stored_filename = doc.stored_filename
                    db_doc.mime_type = doc.mime_type
                    db_doc.file_size = doc.file_size
                    db_doc.document_type = doc.document_type.value
                    db_doc.width = doc.width
                    db_doc.height = doc.height
                    db_doc.page_count = doc.page_count
                    db_doc.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            logger.warning("Could not persist document to DB: %s", exc)

    def _load_from_db(self, doc_id: str) -> Optional[DocumentMetadata]:
        """Try to load document from the database if not in memory."""
        try:
            from app.db.database import SessionLocal
            from app.db.models import Document as DbDocument

            with SessionLocal() as db:
                db_doc = db.query(DbDocument).filter(DbDocument.id == doc_id).first()
                if db_doc:
                    meta = DocumentMetadata(
                        id=db_doc.id,
                        user_id=db_doc.user_id,
                        original_filename=db_doc.original_filename,
                        stored_filename=db_doc.stored_filename,
                        mime_type=db_doc.mime_type,
                        file_size=db_doc.file_size,
                        document_type=DocumentType(db_doc.document_type),
                        width=db_doc.width,
                        height=db_doc.height,
                        page_count=db_doc.page_count,
                        created_at=db_doc.created_at,
                        updated_at=db_doc.updated_at,
                    )
                    self._documents[doc_id] = meta
                    return meta
        except Exception as exc:
            logger.warning("Could not load document from DB: %s", exc)
        return None

    def add(self, doc: DocumentMetadata) -> None:
        with self._lock:
            self._documents[doc.id] = doc
        self._sync_to_db(doc)

    def get(self, doc_id: str) -> Optional[DocumentMetadata]:
        with self._lock:
            doc = self._documents.get(doc_id)
        if doc is not None:
            return doc
        return self._load_from_db(doc_id)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            removed = self._documents.pop(doc_id, None) is not None
        try:
            from app.db.database import SessionLocal
            from app.db.models import Document as DbDocument

            with SessionLocal() as db:
                db_doc = db.query(DbDocument).filter(DbDocument.id == doc_id).first()
                if db_doc:
                    db.delete(db_doc)
                    db.commit()
                    return True
        except Exception as exc:
            logger.warning("Could not delete document from DB: %s", exc)
        return removed

    def list_all(self, user_id: str | None = None) -> list[DocumentMetadata]:
        try:
            from app.db.database import SessionLocal
            from app.db.models import Document as DbDocument

            with SessionLocal() as db:
                query = db.query(DbDocument)
                if user_id is not None:
                    query = query.filter(DbDocument.user_id == user_id)
                db_docs = query.order_by(DbDocument.created_at.desc()).all()
                results = []
                for db_doc in db_docs:
                    meta = DocumentMetadata(
                        id=db_doc.id,
                        user_id=db_doc.user_id,
                        original_filename=db_doc.original_filename,
                        stored_filename=db_doc.stored_filename,
                        mime_type=db_doc.mime_type,
                        file_size=db_doc.file_size,
                        document_type=DocumentType(db_doc.document_type),
                        width=db_doc.width,
                        height=db_doc.height,
                        page_count=db_doc.page_count,
                        created_at=db_doc.created_at,
                        updated_at=db_doc.updated_at,
                    )
                    with self._lock:
                        self._documents[meta.id] = meta
                    results.append(meta)
                return results
        except Exception as exc:
            logger.warning("Could not list documents from DB: %s", exc)
            with self._lock:
                docs = list(self._documents.values())
                if user_id:
                    docs = [d for d in docs if d.user_id == user_id]
                return docs

    def count(self, user_id: str | None = None) -> int:
        return len(self.list_all(user_id=user_id))


# Global singleton
document_store = DocumentStore()
