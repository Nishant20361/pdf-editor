"""Test fixtures and helpers for backend tests."""

from __future__ import annotations

import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
import fitz  # PyMuPDF

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def temp_upload_dir(monkeypatch, tmp_path):
    """Use a temporary directory for uploads during tests."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.config.settings.UPLOAD_DIR", upload_dir)
    return upload_dir


@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    """Create a valid JPEG image in memory."""
    img = Image.new("RGB", (200, 100), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Create a valid PNG image in memory."""
    img = Image.new("RGBA", (300, 200), color=(0, 255, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Create a valid PDF with 3 pages in memory."""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        text_point = fitz.Point(72, 72)
        page.insert_text(text_point, f"Test page {i + 1}", fontsize=24)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.fixture
def sample_single_page_pdf_bytes() -> bytes:
    """Create a valid single-page PDF in memory."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(72, 72), "Single page test", fontsize=18)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.fixture
def oversized_bytes() -> bytes:
    """Create bytes larger than MAX_FILE_SIZE_MB."""
    from app.config import settings
    return b"\x00" * (settings.max_file_size_bytes + 1)


@pytest.fixture
def corrupted_jpeg_bytes() -> bytes:
    """Create bytes with JPEG extension expectations but invalid content."""
    return b"This is not a JPEG file at all, just random text content."


@pytest.fixture
def corrupted_pdf_bytes() -> bytes:
    """Create bytes with PDF extension expectations but invalid content."""
    return b"This is not a PDF file, just garbage data."
