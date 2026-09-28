"""Edit/replacement data model and persistent edit store."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.detection import NormalizedBoundingBox

logger = logging.getLogger(__name__)


class BackgroundCleanupMethod(str, Enum):
    SOLID = "solid"
    INPAINT = "inpaint"
    BLUR = "blur"
    MANUAL_COLOR = "manual_color"


class EditRecord(BaseModel):
    """A single text-replacement edit."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str
    page_number: int = Field(ge=0)
    original_text: str
    replacement_text: str = Field(max_length=2000)
    original_box: NormalizedBoundingBox
    current_box: NormalizedBoundingBox
    detection_source: str = "native_pdf"
    ocr_confidence: float = Field(default=1.0, ge=0, le=1)
    font_family: str = "Arial"
    font_size: float = Field(default=14.0, gt=0, le=500)
    font_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    font_weight: str = "normal"  # "normal" | "bold"
    font_style: str = "normal"  # "normal" | "italic"
    rotation: float = 0.0
    alignment: str = "left"  # "left" | "center" | "right"
    letter_spacing: float = 0.0
    line_height: float = 1.2
    bg_cleanup: BackgroundCleanupMethod = BackgroundCleanupMethod.SOLID
    bg_color: Optional[str] = None  # Manual bg color override (#rrggbb)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied: bool = False
    revision: int = 1

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CreateEditRequest(BaseModel):
    page_number: int = Field(ge=0)
    original_text: str = Field(min_length=0, max_length=2000)
    replacement_text: str = Field(min_length=1, max_length=2000)
    original_box: NormalizedBoundingBox
    current_box: Optional[NormalizedBoundingBox] = None
    detection_source: str = "native_pdf"
    ocr_confidence: float = Field(default=1.0, ge=0, le=1)
    font_family: str = "Arial"
    font_size: float = Field(default=14.0, gt=0, le=500)
    font_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    font_weight: str = "normal"
    font_style: str = "normal"
    rotation: float = 0.0
    alignment: str = "left"
    letter_spacing: float = 0.0
    line_height: float = 1.2
    bg_cleanup: BackgroundCleanupMethod = BackgroundCleanupMethod.SOLID
    bg_color: Optional[str] = None


class UpdateEditRequest(BaseModel):
    replacement_text: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    current_box: Optional[NormalizedBoundingBox] = None
    font_family: Optional[str] = None
    font_size: Optional[float] = Field(default=None, gt=0, le=500)
    font_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    font_weight: Optional[str] = None
    font_style: Optional[str] = None
    rotation: Optional[float] = None
    alignment: Optional[str] = None
    letter_spacing: Optional[float] = None
    line_height: Optional[float] = None
    bg_cleanup: Optional[BackgroundCleanupMethod] = None
    bg_color: Optional[str] = None


# ---- Persistent edit store with undo/redo ----

class _HistoryEntry:
    __slots__ = ("edits",)
    def __init__(self, edits: dict[str, EditRecord]):
        self.edits = {k: v.model_copy(deep=True) for k, v in edits.items()}


class EditStore:
    """Thread-safe per-document edit store with undo/redo and DB persistence."""

    def __init__(self) -> None:
        self._edits: dict[str, dict[str, EditRecord]] = {}  # doc_id -> {edit_id -> edit}
        self._undo: dict[str, list[_HistoryEntry]] = {}
        self._redo: dict[str, list[_HistoryEntry]] = {}
        self._lock = threading.Lock()

    def _sync_to_db(self, doc_id: str) -> None:
        """Synchronize current in-memory edits for document to database."""
        try:
            from app.db.database import SessionLocal
            from app.db.models import ReplacementEdit as DbEdit

            current_edits = list(self._edits.get(doc_id, {}).values())
            with SessionLocal() as db:
                # Remove stale edits not present in current list
                current_ids = {e.id for e in current_edits}
                db.query(DbEdit).filter(
                    DbEdit.document_id == doc_id,
                    ~DbEdit.id.in_(current_ids) if current_ids else True,
                ).delete(synchronize_session=False)

                for e in current_edits:
                    db_edit = db.query(DbEdit).filter(DbEdit.id == e.id).first()
                    if not db_edit:
                        db_edit = DbEdit(
                            id=e.id,
                            document_id=doc_id,
                            page_number=e.page_number,
                            x=e.original_box.x,
                            y=e.original_box.y,
                            width=e.original_box.width,
                            height=e.original_box.height,
                            original_text=e.original_text,
                            replacement_text=e.replacement_text,
                            detection_source=e.detection_source,
                            ocr_confidence=e.ocr_confidence,
                            font_family=e.font_family,
                            font_size=e.font_size,
                            font_color=e.font_color,
                            font_weight=e.font_weight,
                            font_style=e.font_style,
                            rotation=e.rotation,
                            alignment=e.alignment,
                            letter_spacing=e.letter_spacing,
                            line_height=e.line_height,
                            bg_cleanup=e.bg_cleanup.value if isinstance(e.bg_cleanup, BackgroundCleanupMethod) else str(e.bg_cleanup),
                            bg_color=e.bg_color,
                            applied=e.applied,
                            revision=e.revision,
                        )
                        db.add(db_edit)
                    else:
                        db_edit.replacement_text = e.replacement_text
                        db_edit.font_family = e.font_family
                        db_edit.font_size = e.font_size
                        db_edit.font_color = e.font_color
                        db_edit.font_weight = e.font_weight
                        db_edit.font_style = e.font_style
                        db_edit.rotation = e.rotation
                        db_edit.alignment = e.alignment
                        db_edit.letter_spacing = e.letter_spacing
                        db_edit.line_height = e.line_height
                        db_edit.bg_cleanup = e.bg_cleanup.value if isinstance(e.bg_cleanup, BackgroundCleanupMethod) else str(e.bg_cleanup)
                        db_edit.bg_color = e.bg_color
                        db_edit.applied = e.applied
                        db_edit.revision = e.revision
                        db_edit.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            logger.warning("Could not sync edits to DB for doc %s: %s", doc_id, exc)

    def _load_from_db(self, doc_id: str) -> None:
        """Load edits from database if not present in memory."""
        try:
            from app.db.database import SessionLocal
            from app.db.models import ReplacementEdit as DbEdit

            with SessionLocal() as db:
                db_edits = db.query(DbEdit).filter(DbEdit.document_id == doc_id).all()
                if db_edits:
                    edits_map = {}
                    for de in db_edits:
                        box = NormalizedBoundingBox(x=de.x, y=de.y, width=de.width, height=de.height)
                        rec = EditRecord(
                            id=de.id,
                            document_id=doc_id,
                            page_number=de.page_number,
                            original_text=de.original_text,
                            replacement_text=de.replacement_text,
                            original_box=box,
                            current_box=box,
                            detection_source=de.detection_source,
                            ocr_confidence=de.ocr_confidence,
                            font_family=de.font_family,
                            font_size=de.font_size,
                            font_color=de.font_color,
                            font_weight=de.font_weight,
                            font_style=de.font_style,
                            rotation=de.rotation,
                            alignment=de.alignment,
                            letter_spacing=de.letter_spacing,
                            line_height=de.line_height,
                            bg_cleanup=BackgroundCleanupMethod(de.bg_cleanup),
                            bg_color=de.bg_color,
                            applied=de.applied,
                            revision=de.revision,
                        )
                        edits_map[de.id] = rec
                    self._edits[doc_id] = edits_map
        except Exception as exc:
            logger.warning("Could not load edits from DB for doc %s: %s", doc_id, exc)

    def _snapshot(self, doc_id: str) -> None:
        edits = self._edits.get(doc_id, {})
        self._undo.setdefault(doc_id, []).append(_HistoryEntry(edits))
        self._redo[doc_id] = []
        if len(self._undo[doc_id]) > 100:
            self._undo[doc_id] = self._undo[doc_id][-100:]

    def add(self, edit: EditRecord) -> EditRecord:
        with self._lock:
            if edit.document_id not in self._edits:
                self._load_from_db(edit.document_id)
            self._snapshot(edit.document_id)
            self._edits.setdefault(edit.document_id, {})[edit.id] = edit
        self._sync_to_db(edit.document_id)
        return edit

    def get(self, doc_id: str, edit_id: str) -> Optional[EditRecord]:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            return self._edits.get(doc_id, {}).get(edit_id)

    def update(self, doc_id: str, edit_id: str, data: UpdateEditRequest) -> Optional[EditRecord]:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            edit = self._edits.get(doc_id, {}).get(edit_id)
            if edit is None:
                return None
            self._snapshot(doc_id)
            for field, value in data.model_dump(exclude_none=True).items():
                setattr(edit, field, value)
            edit.revision += 1
            edit.timestamp = datetime.now(timezone.utc)
        self._sync_to_db(doc_id)
        return edit

    def delete(self, doc_id: str, edit_id: str) -> bool:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            edits = self._edits.get(doc_id, {})
            if edit_id not in edits:
                return False
            self._snapshot(doc_id)
            del edits[edit_id]
        self._sync_to_db(doc_id)
        return True

    def list_edits(self, doc_id: str, page: int | None = None) -> list[EditRecord]:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            edits = list(self._edits.get(doc_id, {}).values())
            if page is not None:
                edits = [e for e in edits if e.page_number == page]
            return edits

    def undo(self, doc_id: str) -> bool:
        with self._lock:
            stack = self._undo.get(doc_id, [])
            if not stack:
                return False
            current = self._edits.get(doc_id, {})
            self._redo.setdefault(doc_id, []).append(_HistoryEntry(current))
            entry = stack.pop()
            self._edits[doc_id] = entry.edits
        self._sync_to_db(doc_id)
        return True

    def redo(self, doc_id: str) -> bool:
        with self._lock:
            stack = self._redo.get(doc_id, [])
            if not stack:
                return False
            current = self._edits.get(doc_id, {})
            self._undo.setdefault(doc_id, []).append(_HistoryEntry(current))
            entry = stack.pop()
            self._edits[doc_id] = entry.edits
        self._sync_to_db(doc_id)
        return True

    def reset_page(self, doc_id: str, page_number: int) -> int:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            edits = self._edits.get(doc_id, {})
            to_remove = [eid for eid, e in edits.items() if e.page_number == page_number]
            if not to_remove:
                return 0
            self._snapshot(doc_id)
            for eid in to_remove:
                del edits[eid]
        self._sync_to_db(doc_id)
        return len(to_remove)

    def reset_document(self, doc_id: str) -> int:
        with self._lock:
            if doc_id not in self._edits:
                self._load_from_db(doc_id)
            edits = self._edits.get(doc_id, {})
            count = len(edits)
            if count == 0:
                return 0
            self._snapshot(doc_id)
            self._edits[doc_id] = {}
        self._sync_to_db(doc_id)
        return count

    def clear_document(self, doc_id: str) -> None:
        """Remove all data for a document (called on document delete)."""
        with self._lock:
            self._edits.pop(doc_id, None)
            self._undo.pop(doc_id, None)
            self._redo.pop(doc_id, None)
        try:
            from app.db.database import SessionLocal
            from app.db.models import ReplacementEdit as DbEdit

            with SessionLocal() as db:
                db.query(DbEdit).filter(DbEdit.document_id == doc_id).delete(synchronize_session=False)
                db.commit()
        except Exception as exc:
            logger.warning("Could not clear edits from DB: %s", exc)


edit_store = EditStore()
