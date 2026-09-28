"""Phase 3 tests — text replacement engine."""

from __future__ import annotations

import json
from io import BytesIO

import fitz
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.models.edit import edit_store

client = TestClient(app)


# ---- helpers ----

def _upload_jpeg(width=200, height=100):
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    resp = client.post("/api/upload", files={"file": ("test.jpg", buf.getvalue(), "image/jpeg")})
    assert resp.status_code == 201
    return resp.json()


def _upload_pdf(pages=1, text="Hello World"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text(fitz.Point(72, 100), f"{text} page {i+1}", fontsize=24)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    resp = client.post("/api/upload", files={"file": ("test.pdf", buf.getvalue(), "application/pdf")})
    assert resp.status_code == 201
    return resp.json()


def _make_edit(doc_id, page=0, original="Hello", replacement="Goodbye", **kwargs):
    body = {
        "page_number": page,
        "original_text": original,
        "replacement_text": replacement,
        "original_box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.05},
        "font_family": "Arial",
        "font_size": 24,
        "font_color": "#000000",
        **kwargs,
    }
    return client.post(f"/api/documents/{doc_id}/edits", json=body)


# ==== CRUD tests ====

class TestEditCrud:
    def test_create_edit(self):
        doc = _upload_jpeg()
        resp = _make_edit(doc["id"])
        assert resp.status_code == 201
        data = resp.json()
        assert data["replacement_text"] == "Goodbye"
        assert data["document_id"] == doc["id"]
        assert "id" in data

    def test_list_edits(self):
        doc = _upload_jpeg()
        _make_edit(doc["id"], replacement="A")
        _make_edit(doc["id"], replacement="B")
        resp = client.get(f"/api/documents/{doc['id']}/edits")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_update_edit(self):
        doc = _upload_jpeg()
        edit = _make_edit(doc["id"]).json()
        resp = client.patch(
            f"/api/documents/{doc['id']}/edits/{edit['id']}",
            json={"replacement_text": "Updated", "font_size": 32},
        )
        assert resp.status_code == 200
        assert resp.json()["replacement_text"] == "Updated"
        assert resp.json()["font_size"] == 32

    def test_delete_edit(self):
        doc = _upload_jpeg()
        edit = _make_edit(doc["id"]).json()
        resp = client.delete(f"/api/documents/{doc['id']}/edits/{edit['id']}")
        assert resp.status_code == 200
        # Verify deleted
        resp2 = client.get(f"/api/documents/{doc['id']}/edits/{edit['id']}")
        assert resp2.status_code == 404


# ==== Undo / Redo ====

class TestUndoRedo:
    def test_undo_redo(self):
        doc = _upload_jpeg()
        _make_edit(doc["id"], replacement="First")
        edits = client.get(f"/api/documents/{doc['id']}/edits").json()
        assert edits["count"] == 1

        # Undo should remove the edit
        resp = client.post(f"/api/documents/{doc['id']}/edits/undo")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(resp.json()["edits"]) == 0

        # Redo should restore it
        resp = client.post(f"/api/documents/{doc['id']}/edits/redo")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(resp.json()["edits"]) == 1

    def test_undo_empty_fails_gracefully(self):
        doc = _upload_jpeg()
        resp = client.post(f"/api/documents/{doc['id']}/edits/undo")
        assert resp.json()["success"] is False


# ==== Reset ====

class TestReset:
    def test_reset_page(self):
        doc = _upload_pdf(pages=2)
        _make_edit(doc["id"], page=0, replacement="A")
        _make_edit(doc["id"], page=1, replacement="B")
        resp = client.post(f"/api/documents/{doc['id']}/edits/reset-page/0")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 1
        # Page 1 edit should remain
        edits = client.get(f"/api/documents/{doc['id']}/edits").json()
        assert edits["count"] == 1
        assert edits["edits"][0]["page_number"] == 1

    def test_reset_document(self):
        doc = _upload_pdf(pages=2)
        _make_edit(doc["id"], page=0, replacement="A")
        _make_edit(doc["id"], page=1, replacement="B")
        resp = client.post(f"/api/documents/{doc['id']}/edits/reset")
        assert resp.json()["removed"] == 2
        edits = client.get(f"/api/documents/{doc['id']}/edits").json()
        assert edits["count"] == 0


# ==== Image replacement ====

class TestImageReplacement:
    def test_image_preview_with_edits(self):
        doc = _upload_jpeg(width=400, height=200)
        _make_edit(doc["id"], replacement="Replaced Text")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # Verify it's a valid image
        img = Image.open(BytesIO(resp.content))
        assert img.size[0] > 0

    def test_image_preview_no_edits(self):
        doc = _upload_jpeg()
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200

    def test_multiple_replacements_on_image(self):
        doc = _upload_jpeg(width=600, height=400)
        _make_edit(doc["id"], replacement="First", original_box={"x": 0.05, "y": 0.1, "width": 0.3, "height": 0.05})
        _make_edit(doc["id"], replacement="Second", original_box={"x": 0.05, "y": 0.3, "width": 0.3, "height": 0.05})
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200
        img = Image.open(BytesIO(resp.content))
        assert img.size == (600, 400)


def _make_edit_with_box(doc_id, **kwargs):
    body = {
        "page_number": 0,
        "original_text": "orig",
        "replacement_text": "rep",
        "original_box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.05},
        "font_family": "Arial",
        "font_size": 24,
        "font_color": "#000000",
        **kwargs,
    }
    return client.post(f"/api/documents/{doc_id}/edits", json=body)


# ==== Native PDF replacement ====

class TestNativePdfReplacement:
    def test_pdf_preview_with_edits(self):
        doc = _upload_pdf(pages=1, text="Hello World")
        _make_edit(doc["id"], replacement="Bye World")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        img = Image.open(BytesIO(resp.content))
        assert img.size[0] > 0

    def test_multipage_pdf_edits(self):
        doc = _upload_pdf(pages=3, text="Test")
        _make_edit(doc["id"], page=0, replacement="Page0")
        _make_edit(doc["id"], page=2, replacement="Page2")

        resp0 = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp0.status_code == 200
        resp1 = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=1")
        assert resp1.status_code == 200
        resp2 = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=2")
        assert resp2.status_code == 200


# ==== Font and colour ====

class TestFontAndColour:
    def test_font_and_color_preservation(self):
        doc = _upload_jpeg(width=400, height=200)
        resp = _make_edit(
            doc["id"],
            replacement="Colored",
            font_color="#ff0000",
            font_size=36,
            font_weight="bold",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["font_color"] == "#ff0000"
        assert data["font_size"] == 36
        assert data["font_weight"] == "bold"

        preview = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert preview.status_code == 200


# ==== Long text fitting ====

class TestLongTextFitting:
    def test_long_replacement_text(self):
        doc = _upload_jpeg(width=400, height=200)
        _make_edit(doc["id"], replacement="This is a very long replacement text that should auto-shrink to fit")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200
        img = Image.open(BytesIO(resp.content))
        assert img.size == (400, 200)  # Image size preserved


# ==== Background cleanup methods ====

class TestBackgroundCleanup:
    def test_solid_cleanup(self):
        doc = _upload_jpeg(width=300, height=200)
        _make_edit(doc["id"], replacement="Solid", bg_cleanup="solid")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200

    def test_inpaint_cleanup(self):
        doc = _upload_jpeg(width=300, height=200)
        _make_edit(doc["id"], replacement="Inpaint", bg_cleanup="inpaint")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200

    def test_blur_cleanup(self):
        doc = _upload_jpeg(width=300, height=200)
        _make_edit(doc["id"], replacement="Blur", bg_cleanup="blur")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200

    def test_manual_color_cleanup(self):
        doc = _upload_jpeg(width=300, height=200)
        _make_edit(doc["id"], replacement="Manual", bg_cleanup="manual_color", bg_color="#cccccc")
        resp = client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")
        assert resp.status_code == 200


# ==== Validation ====

class TestEditValidation:
    def test_invalid_document(self):
        resp = _make_edit("nonexistent123")
        assert resp.status_code == 404

    def test_page_out_of_range(self):
        doc = _upload_jpeg()
        resp = _make_edit(doc["id"], page=5)
        assert resp.status_code == 400

    def test_invalid_color_format(self):
        doc = _upload_jpeg()
        resp = _make_edit(doc["id"], font_color="notacolor")
        assert resp.status_code == 422

    def test_font_size_zero(self):
        doc = _upload_jpeg()
        resp = _make_edit(doc["id"], font_size=0)
        assert resp.status_code == 422

    def test_edit_nonexistent_edit(self):
        doc = _upload_jpeg()
        resp = client.patch(f"/api/documents/{doc['id']}/edits/fake123", json={"replacement_text": "x"})
        assert resp.status_code == 404

    def test_delete_nonexistent_edit(self):
        doc = _upload_jpeg()
        resp = client.delete(f"/api/documents/{doc['id']}/edits/fake123")
        assert resp.status_code == 404


# ==== Original file preservation ====

class TestOriginalPreservation:
    def test_original_unchanged_after_edits(self):
        doc = _upload_jpeg(width=200, height=100)
        # Get original preview
        original = client.get(f"/api/documents/{doc['id']}/preview").content

        # Create edits
        _make_edit(doc["id"], replacement="Modified")
        client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")

        # Original should be unchanged
        after = client.get(f"/api/documents/{doc['id']}/preview").content
        assert original == after

    def test_pdf_original_unchanged(self):
        doc = _upload_pdf(pages=1, text="Original")
        original = client.get(f"/api/documents/{doc['id']}/preview?page=0").content

        _make_edit(doc["id"], replacement="Changed")
        client.get(f"/api/documents/{doc['id']}/preview-with-edits?page=0")

        after = client.get(f"/api/documents/{doc['id']}/preview?page=0").content
        assert original == after
