"""Phase 4 tests — export and download pipeline."""

from __future__ import annotations

import zipfile
from io import BytesIO

import fitz
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.models.export import parse_page_range

client = TestClient(app)


# ---- helpers ----

def _upload_jpeg(width=200, height=100):
    img = Image.new("RGB", (width, height), color=(200, 220, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    resp = client.post("/api/upload", files={"file": ("photo.jpg", buf.getvalue(), "image/jpeg")})
    assert resp.status_code == 201
    return resp.json()


def _upload_png_rgba(width=200, height=100):
    img = Image.new("RGBA", (width, height), color=(200, 220, 255, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    resp = client.post("/api/upload", files={"file": ("transparent.png", buf.getvalue(), "image/png")})
    assert resp.status_code == 201
    return resp.json()


def _upload_pdf(pages=3, text="Hello World"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text(fitz.Point(72, 100), f"{text} page {i+1}", fontsize=24)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    resp = client.post("/api/upload", files={"file": ("report.pdf", buf.getvalue(), "application/pdf")})
    assert resp.status_code == 201
    return resp.json()


def _add_edit(doc_id, page=0, replacement="Replaced", **kw):
    body = {
        "page_number": page,
        "original_text": "Hello",
        "replacement_text": replacement,
        "original_box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.05},
        "font_family": "Arial",
        "font_size": 24,
        "font_color": "#000000",
        **kw,
    }
    resp = client.post(f"/api/documents/{doc_id}/edits", json=body)
    assert resp.status_code == 201
    return resp.json()


def _export(doc_id, **kw):
    body = {"output_format": "pdf", **kw}
    return client.post(f"/api/documents/{doc_id}/exports", json=body)


# ==== Page range parsing ====

class TestPageRangeParsing:
    def test_single_pages(self):
        assert parse_page_range("1,3,5", 5) == [0, 2, 4]

    def test_range(self):
        assert parse_page_range("1-3", 5) == [0, 1, 2]

    def test_mixed(self):
        assert parse_page_range("1-3,5,8-10", 10) == [0, 1, 2, 4, 7, 8, 9]

    def test_out_of_bounds(self):
        with pytest.raises(ValueError):
            parse_page_range("1-20", 5)

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_page_range("abc", 5)


# ==== Image exports ====

class TestImageExport:
    def test_png_export(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="png")
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "completed"
        assert data["mime_type"] == "image/png"

        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        assert dl.status_code == 200
        img = Image.open(BytesIO(dl.content))
        assert img.format == "PNG"

    def test_jpeg_export(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="jpeg", quality=75)
        data = resp.json()
        assert data["status"] == "completed"
        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        img = Image.open(BytesIO(dl.content))
        assert img.format == "JPEG"

    def test_webp_export(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="webp", quality=80)
        data = resp.json()
        assert data["status"] == "completed"
        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        img = Image.open(BytesIO(dl.content))
        assert img.format == "WEBP"

    def test_transparent_png_export(self):
        doc = _upload_png_rgba()
        resp = _export(doc["id"], output_format="png")
        data = resp.json()
        assert data["status"] == "completed"


# ==== PDF exports ====

class TestPdfExport:
    def test_native_pdf_export(self):
        doc = _upload_pdf(pages=2)
        _add_edit(doc["id"], page=0)
        resp = _export(doc["id"], output_format="pdf")
        data = resp.json()
        assert data["status"] == "completed"
        assert data["page_count"] == 2

        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        assert dl.status_code == 200
        pdf = fitz.open(stream=dl.content, filetype="pdf")
        assert pdf.page_count == 2
        pdf.close()

    def test_flattened_pdf_export(self):
        doc = _upload_pdf(pages=2)
        _add_edit(doc["id"], page=0)
        resp = _export(doc["id"], output_format="pdf_flattened")
        data = resp.json()
        assert data["status"] == "completed"

        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        pdf = fitz.open(stream=dl.content, filetype="pdf")
        assert pdf.page_count == 2
        pdf.close()

    def test_multipage_pdf_export(self):
        doc = _upload_pdf(pages=5)
        _add_edit(doc["id"], page=0, replacement="Page1")
        _add_edit(doc["id"], page=2, replacement="Page3")
        _add_edit(doc["id"], page=4, replacement="Page5")
        resp = _export(doc["id"])
        data = resp.json()
        assert data["status"] == "completed"
        assert data["page_count"] == 5

    def test_zip_export(self):
        doc = _upload_pdf(pages=3)
        _add_edit(doc["id"], page=0)
        resp = _export(doc["id"], output_format="zip_images", image_format_for_zip="png")
        data = resp.json()
        assert data["status"] == "completed"

        dl = client.get(f"/api/documents/{doc['id']}/exports/{data['id']}/download")
        zf = zipfile.ZipFile(BytesIO(dl.content))
        assert len(zf.namelist()) == 3
        for name in zf.namelist():
            assert name.endswith(".png")
        zf.close()


# ==== Page selection ====

class TestPageSelection:
    def test_current_page_export(self):
        doc = _upload_pdf(pages=3)
        _add_edit(doc["id"], page=1)
        resp = _export(doc["id"], page_selection="current", current_page=1)
        data = resp.json()
        assert data["status"] == "completed"
        assert data["page_count"] == 1

    def test_edited_pages_export(self):
        doc = _upload_pdf(pages=5)
        _add_edit(doc["id"], page=1)
        _add_edit(doc["id"], page=3)
        resp = _export(doc["id"], page_selection="edited")
        data = resp.json()
        assert data["status"] == "completed"
        assert data["page_count"] == 2

    def test_custom_range_export(self):
        doc = _upload_pdf(pages=5)
        resp = _export(doc["id"], page_selection="custom", custom_pages="1-3,5")
        data = resp.json()
        assert data["status"] == "completed"
        assert data["page_count"] == 4

    def test_invalid_page_range(self):
        doc = _upload_pdf(pages=3)
        resp = _export(doc["id"], page_selection="custom", custom_pages="1-10")
        assert resp.status_code == 400


# ==== Unicode ====

class TestUnicodeExport:
    def test_unicode_replacement_text(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"], replacement="श्रबानी Kumar ®")
        resp = _export(doc["id"], output_format="png")
        data = resp.json()
        assert data["status"] == "completed"


# ==== Font fallback ====

class TestFontFallback:
    def test_unknown_font_fallback(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"], replacement="Fallback", font_family="NonexistentFont9999")
        resp = _export(doc["id"], output_format="png")
        data = resp.json()
        assert data["status"] == "completed"


# ==== Validation ====

class TestExportValidation:
    def test_invalid_document(self):
        resp = _export("nonexistent123")
        assert resp.status_code == 404

    def test_invalid_export_id(self):
        doc = _upload_jpeg()
        resp = client.get(f"/api/documents/{doc['id']}/exports/fake123")
        assert resp.status_code == 404

    def test_download_not_ready(self):
        doc = _upload_jpeg()
        # No export exists
        resp = client.get(f"/api/documents/{doc['id']}/exports/fake123/download")
        assert resp.status_code == 404

    def test_delete_export(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        export_resp = _export(doc["id"], output_format="png")
        eid = export_resp.json()["id"]
        del_resp = client.delete(f"/api/documents/{doc['id']}/exports/{eid}")
        assert del_resp.status_code == 200
        # Should be gone
        get_resp = client.get(f"/api/documents/{doc['id']}/exports/{eid}")
        assert get_resp.status_code == 404


# ==== Filename safety ====

class TestFilenameSafety:
    def test_safe_default_filename(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="png")
        data = resp.json()
        assert "photo_edited" in data["filename"]

    def test_custom_filename(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="png", filename="my_output")
        data = resp.json()
        assert data["filename"] == "my_output.png"

    def test_unsafe_filename_sanitized(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="png", filename="../../etc/passwd")
        data = resp.json()
        assert ".." not in data["filename"]
        assert "/" not in data["filename"]


# ==== Original preservation ====

class TestOriginalPreservation:
    def test_original_unchanged_after_export(self):
        doc = _upload_jpeg()
        orig = client.get(f"/api/documents/{doc['id']}/preview").content

        _add_edit(doc["id"], replacement="Changed")
        _export(doc["id"], output_format="png")

        after = client.get(f"/api/documents/{doc['id']}/preview").content
        assert orig == after

    def test_pdf_original_unchanged(self):
        doc = _upload_pdf(pages=1)
        orig = client.get(f"/api/documents/{doc['id']}/preview?page=0").content

        _add_edit(doc["id"], replacement="Changed")
        _export(doc["id"])

        after = client.get(f"/api/documents/{doc['id']}/preview?page=0").content
        assert orig == after


# ==== Export status polling ====

class TestExportStatus:
    def test_completed_status(self):
        doc = _upload_jpeg()
        _add_edit(doc["id"])
        resp = _export(doc["id"], output_format="png")
        data = resp.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert data["file_size"] > 0
        assert data["completed_at"] is not None
