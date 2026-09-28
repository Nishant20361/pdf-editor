"""SQLAlchemy database models for persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=True, nullable=False)
    role = Column(String(50), default="user", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    sessions = relationship("SessionToken", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    export_jobs = relationship("ExportJob", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="user", cascade="all, delete-orphan")


class SessionToken(Base):
    """Active session / refresh token."""

    __tablename__ = "session_tokens"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")


class Document(Base):
    """Uploaded document metadata."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    document_type = Column(String(20), nullable=False)  # "image" or "pdf"
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    page_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="documents")
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    detections = relationship("TextDetection", back_populates="document", cascade="all, delete-orphan")
    edits = relationship("ReplacementEdit", back_populates="document", cascade="all, delete-orphan")
    export_jobs = relationship("ExportJob", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    """Rendered page preview info for PDF/multipage."""

    __tablename__ = "document_pages"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)  # 0-indexed
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    preview_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    document = relationship("Document", back_populates="pages")

    __table_args__ = (
        Index("idx_doc_page", "document_id", "page_number", unique=True),
    )


class TextDetection(Base):
    """Stored text search/OCR detection results."""

    __tablename__ = "text_detections"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    search_term = Column(String(255), nullable=True)
    occurrences_json = Column(Text, nullable=False)  # JSON-encoded occurrences list
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    document = relationship("Document", back_populates="detections")


class ReplacementEdit(Base):
    """Stored text replacement edit."""

    __tablename__ = "replacement_edits"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    original_text = Column(Text, nullable=False)
    replacement_text = Column(Text, nullable=False)
    detection_source = Column(String(50), default="native_pdf", nullable=False)
    ocr_confidence = Column(Float, default=1.0, nullable=False)
    font_family = Column(String(100), default="Arial", nullable=False)
    font_size = Column(Float, default=14.0, nullable=False)
    font_color = Column(String(10), default="#000000", nullable=False)
    font_weight = Column(String(20), default="normal", nullable=False)
    font_style = Column(String(20), default="normal", nullable=False)
    rotation = Column(Float, default=0.0, nullable=False)
    alignment = Column(String(20), default="left", nullable=False)
    letter_spacing = Column(Float, default=0.0, nullable=False)
    line_height = Column(Float, default=1.2, nullable=False)
    bg_cleanup = Column(String(30), default="solid", nullable=False)
    bg_color = Column(String(20), nullable=True)
    applied = Column(Boolean, default=False, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    document = relationship("Document", back_populates="edits")


class EditHistory(Base):
    """Undo/redo state history for edits."""

    __tablename__ = "edit_history"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    edit_id = Column(String(36), nullable=True)
    action = Column(String(50), nullable=False)  # "create", "update", "delete", "reset"
    state_json = Column(Text, nullable=False)  # JSON-encoded snapshot
    revision = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExportJob(Base):
    """Export job record."""

    __tablename__ = "export_jobs"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    output_format = Column(String(20), nullable=False)
    mode = Column(String(30), default="preserve", nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    page_count = Column(Integer, default=1, nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    status = Column(String(30), default="pending", nullable=False)  # pending, processing, completed, failed
    storage_path = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="export_jobs")
    user = relationship("User", back_populates="export_jobs")


class UsageRecord(Base):
    """Usage tracking per user."""

    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    metric = Column(String(50), nullable=False, index=True)  # "exports", "ocr_calls", "storage_bytes"
    count = Column(Integer, default=1, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="usage_records")


class AuditEvent(Base):
    """Audit log for security, privacy, and tracking."""

    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)  # "login", "register", "upload", "export", "delete"
    resource_type = Column(String(50), nullable=True)  # "document", "user", "export"
    resource_id = Column(String(36), nullable=True)
    details_json = Column(Text, nullable=True)  # Non-sensitive details only
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="audit_events")
