"""Tests for file upload and validation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestValidImageUpload:
    """Test uploading valid image files."""

    def test_upload_valid_jpeg(self, sample_jpeg_bytes):
        """JPEG upload should succeed with correct metadata."""
        response = client.post(
            "/api/upload",
            files={"file": ("test_photo.jpg", sample_jpeg_bytes, "image/jpeg")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["document_type"] == "image"
        assert data["mime_type"] == "image/jpeg"
        assert data["width"] == 200
        assert data["height"] == 100
        assert data["page_count"] == 1
        assert "id" in data
        assert data["file_size"] == len(sample_jpeg_bytes)

    def test_upload_valid_png(self, sample_png_bytes):
        """PNG upload should succeed with correct metadata."""
        response = client.post(
            "/api/upload",
            files={"file": ("screenshot.png", sample_png_bytes, "image/png")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["document_type"] == "image"
        assert data["mime_type"] == "image/png"
        assert data["width"] == 300
        assert data["height"] == 200

    def test_upload_returns_unique_ids(self, sample_jpeg_bytes):
        """Each upload should return a unique document ID."""
        r1 = client.post("/api/upload", files={"file": ("a.jpg", sample_jpeg_bytes, "image/jpeg")})
        r2 = client.post("/api/upload", files={"file": ("b.jpg", sample_jpeg_bytes, "image/jpeg")})
        assert r1.json()["id"] != r2.json()["id"]


class TestValidPdfUpload:
    """Test uploading valid PDF files."""

    def test_upload_valid_pdf(self, sample_pdf_bytes):
        """PDF upload should succeed with page count."""
        response = client.post(
            "/api/upload",
            files={"file": ("document.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["document_type"] == "pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["page_count"] == 3
        assert data["width"] > 0
        assert data["height"] > 0

    def test_upload_single_page_pdf(self, sample_single_page_pdf_bytes):
        """Single-page PDF should report page_count=1."""
        response = client.post(
            "/api/upload",
            files={"file": ("single.pdf", sample_single_page_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        assert response.json()["page_count"] == 1


class TestUnsupportedFileRejection:
    """Test rejection of unsupported file types."""

    def test_reject_txt_file(self):
        """Text files should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("readme.txt", b"Hello world", "text/plain")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "UNSUPPORTED_EXTENSION"

    def test_reject_exe_file(self):
        """Executable files should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("malware.exe", b"\x4d\x5a" + b"\x00" * 100, "application/octet-stream")},
        )
        assert response.status_code == 422
        assert "not supported" in response.json()["detail"]["error"].lower() or \
               response.json()["detail"]["error_code"] == "UNSUPPORTED_EXTENSION"

    def test_reject_html_file(self):
        """HTML files should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("page.html", b"<html></html>", "text/html")},
        )
        assert response.status_code == 422

    def test_reject_no_extension(self):
        """Files without extension should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("noextension", b"\x00" * 100, "application/octet-stream")},
        )
        assert response.status_code == 422


class TestOversizedFileRejection:
    """Test rejection of files exceeding size limit."""

    def test_reject_oversized_file(self, monkeypatch):
        """Files larger than MAX_FILE_SIZE_MB should be rejected."""
        # Temporarily set a very small limit
        monkeypatch.setattr("app.config.settings.MAX_FILE_SIZE_MB", 0)

        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        tiny_jpeg = buf.getvalue()

        response = client.post(
            "/api/upload",
            files={"file": ("big.jpg", tiny_jpeg, "image/jpeg")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "FILE_TOO_LARGE"

    def test_reject_empty_file(self):
        """Empty files should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "EMPTY_FILE"


class TestCorruptedFileRejection:
    """Test rejection of files with invalid signatures."""

    def test_reject_corrupted_jpeg(self, corrupted_jpeg_bytes):
        """Files claiming to be JPEG but with wrong magic bytes should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("fake.jpg", corrupted_jpeg_bytes, "image/jpeg")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "INVALID_SIGNATURE"

    def test_reject_corrupted_pdf(self, corrupted_pdf_bytes):
        """Files claiming to be PDF but with wrong magic bytes should be rejected."""
        response = client.post(
            "/api/upload",
            files={"file": ("fake.pdf", corrupted_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "INVALID_SIGNATURE"

    def test_reject_png_with_jpeg_extension(self, sample_png_bytes):
        """PNG data with .jpg extension should be rejected (mismatched signature)."""
        response = client.post(
            "/api/upload",
            files={"file": ("actually_png.jpg", sample_png_bytes, "image/jpeg")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "INVALID_SIGNATURE"


class TestDocumentCrud:
    """Test document CRUD operations."""

    def test_get_document(self, sample_jpeg_bytes):
        """Should retrieve document metadata after upload."""
        upload_res = client.post(
            "/api/upload",
            files={"file": ("test.jpg", sample_jpeg_bytes, "image/jpeg")},
        )
        doc_id = upload_res.json()["id"]

        get_res = client.get(f"/api/documents/{doc_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == doc_id

    def test_get_nonexistent_document(self):
        """Should return 404 for nonexistent document."""
        response = client.get("/api/documents/nonexistent123")
        assert response.status_code == 404

    def test_delete_document(self, sample_jpeg_bytes):
        """Should delete document and return success."""
        upload_res = client.post(
            "/api/upload",
            files={"file": ("delete_me.jpg", sample_jpeg_bytes, "image/jpeg")},
        )
        doc_id = upload_res.json()["id"]

        delete_res = client.delete(f"/api/documents/{doc_id}")
        assert delete_res.status_code == 200

        # Should be gone
        get_res = client.get(f"/api/documents/{doc_id}")
        assert get_res.status_code == 404


class TestPreview:
    """Test preview generation."""

    def test_image_preview(self, sample_jpeg_bytes):
        """Should return a PNG preview for images."""
        upload_res = client.post(
            "/api/upload",
            files={"file": ("preview.jpg", sample_jpeg_bytes, "image/jpeg")},
        )
        doc_id = upload_res.json()["id"]

        preview_res = client.get(f"/api/documents/{doc_id}/preview")
        assert preview_res.status_code == 200
        assert preview_res.headers["content-type"] == "image/png"
        assert len(preview_res.content) > 0

    def test_pdf_page_preview(self, sample_pdf_bytes):
        """Should return PNG previews for PDF pages."""
        upload_res = client.post(
            "/api/upload",
            files={"file": ("pages.pdf", sample_pdf_bytes, "application/pdf")},
        )
        doc_id = upload_res.json()["id"]

        # Page 0
        p0 = client.get(f"/api/documents/{doc_id}/preview?page=0")
        assert p0.status_code == 200
        assert p0.headers["content-type"] == "image/png"

        # Page 2 (last page)
        p2 = client.get(f"/api/documents/{doc_id}/preview?page=2")
        assert p2.status_code == 200

        # Page 3 (out of range)
        p3 = client.get(f"/api/documents/{doc_id}/preview?page=3")
        assert p3.status_code == 400

    def test_preview_nonexistent_document(self):
        """Should return 404 for preview of nonexistent document."""
        response = client.get("/api/documents/fake123/preview")
        assert response.status_code == 404
