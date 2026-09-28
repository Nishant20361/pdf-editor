"""Tests for database persistence, server restart simulation, and edit recovery."""

from io import BytesIO
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import document_store
from app.models.edit import edit_store
from app.models.export import export_store

client = TestClient(app)


def _make_jpeg_bytes() -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (100, 100), color=(0, 255, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestPersistence:
    def test_document_and_edits_survive_cache_clear(self):
        # 1. Upload document
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("persist_test.jpg", _make_jpeg_bytes(), "image/jpeg")},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # 2. Add an edit
        edit_resp = client.post(
            f"/api/documents/{doc_id}/edits",
            json={
                "page_number": 0,
                "original_text": "Original Title",
                "replacement_text": "Persisted Title",
                "original_box": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.08},
                "font_family": "Arial",
                "font_size": 24,
            },
        )
        assert edit_resp.status_code == 201
        edit_id = edit_resp.json()["id"]

        # 3. Simulate server restart by clearing in-memory caches
        document_store._documents.clear()
        edit_store._edits.clear()
        edit_store._undo.clear()
        edit_store._redo.clear()

        # 4. Fetch document again — should recover from DB
        doc_resp = client.get(f"/api/documents/{doc_id}")
        assert doc_resp.status_code == 200
        assert doc_resp.json()["id"] == doc_id
        assert doc_resp.json()["original_filename"] == "persist_test.jpg"

        # 5. Fetch edits again — should recover from DB
        edits_resp = client.get(f"/api/documents/{doc_id}/edits")
        assert edits_resp.status_code == 200
        assert edits_resp.json()["count"] == 1
        recovered_edit = edits_resp.json()["edits"][0]
        assert recovered_edit["id"] == edit_id
        assert recovered_edit["replacement_text"] == "Persisted Title"
        assert recovered_edit["font_size"] == 24

        # 6. Cleanup
        del_resp = client.delete(f"/api/documents/{doc_id}")
        assert del_resp.status_code == 200
