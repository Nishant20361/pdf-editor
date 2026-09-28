"""Normalized text-detection models shared by PDF, OCR, and manual sources."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DetectionSource(str, Enum):
    NATIVE_PDF = "native_pdf"
    OCR = "ocr"
    MANUAL = "manual"


class PageContentType(str, Enum):
    NATIVE = "native"
    SCANNED = "scanned"
    MIXED = "mixed"


class NormalizedBoundingBox(BaseModel):
    """Bounding box expressed as 0..1 fractions of the page/image dimensions."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class FontEstimate(BaseModel):
    family: Optional[str] = None
    size: Optional[float] = None
    color: Optional[str] = None
    bold: bool = False
    italic: bool = False


class TextDetection(BaseModel):
    id: str
    document_id: str
    page_number: int
    text: str
    bounding_box: NormalizedBoundingBox
    confidence: float = Field(ge=0, le=1)
    source: DetectionSource
    font: FontEstimate = Field(default_factory=FontEstimate)
    rotation: float = 0


class PageAnalysis(BaseModel):
    page_number: int
    content_type: PageContentType
    width: float
    height: float


class DetectionRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    case_sensitive: bool = False
    exact_match: bool = False
    page_number: Optional[int] = Field(default=None, ge=0)


class DetectionResponse(BaseModel):
    document_id: str
    query: str
    pages: list[PageAnalysis]
    detections: list[TextDetection]
    ocr_available: bool
    warnings: list[str] = Field(default_factory=list)
