"""Tests for normalized text detection and search."""

from __future__ import annotations

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.services.detection_service import _ocr_detections
from app.services.ocr_service import OcrWord, parse_tesseract_tsv
from app.services.replacement_service import _get_pil_font

client = TestClient(app)


def test_native_pdf_text_detection(sample_pdf_bytes):
    upload = client.post(
        "/api/upload",
        files={"file": ("native.pdf", sample_pdf_bytes, "application/pdf")},
    )
    document_id = upload.json()["id"]
    response = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "Test page", "case_sensitive": False, "exact_match": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["detections"]) == 3
    assert all(item["source"] == "native_pdf" for item in data["detections"])
    assert all(0 <= item["bounding_box"]["x"] <= 1 for item in data["detections"])
    assert all(item["confidence"] == 1 for item in data["detections"])


def test_exact_and_case_sensitive_search(sample_single_page_pdf_bytes):
    upload = client.post(
        "/api/upload",
        files={"file": ("single.pdf", sample_single_page_pdf_bytes, "application/pdf")},
    )
    document_id = upload.json()["id"]
    exact = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "Single page test", "case_sensitive": True, "exact_match": True},
    )
    wrong_case = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "single page test", "case_sensitive": True, "exact_match": True},
    )
    assert len(exact.json()["detections"]) == 1
    assert wrong_case.json()["detections"] == []


def test_page_filter_and_out_of_range(sample_pdf_bytes):
    upload = client.post(
        "/api/upload",
        files={"file": ("pages.pdf", sample_pdf_bytes, "application/pdf")},
    )
    document_id = upload.json()["id"]
    page_two = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "Test", "page_number": 1},
    )
    invalid = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "Test", "page_number": 3},
    )
    assert [item["page_number"] for item in page_two.json()["detections"]] == [1]
    assert invalid.status_code == 400


def test_tesseract_tsv_parser():
    tsv = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t12\t30\t80\t20\t96.5\tHello
5\t1\t1\t1\t1\t2\t100\t30\t60\t20\t88.0\tWorld
5\t1\t1\t1\t1\t3\t170\t30\t20\t20\t-1\t
"""
    words = parse_tesseract_tsv(tsv)
    assert [word.text for word in words] == ["Hello", "World"]
    assert words[0].confidence == 0.965
    assert (words[0].left, words[0].top, words[0].width, words[0].height) == (12, 30, 80, 20)


def test_image_detection_returns_warning_without_ocr(sample_jpeg_bytes, monkeypatch):
    monkeypatch.setattr("app.services.detection_service.is_ocr_available", lambda: False)
    upload = client.post(
        "/api/upload",
        files={"file": ("image.jpg", sample_jpeg_bytes, "image/jpeg")},
    )
    document_id = upload.json()["id"]
    response = client.post(
        f"/api/documents/{document_id}/detect",
        json={"query": "anything"},
    )
    assert response.status_code == 200
    assert response.json()["pages"][0]["content_type"] == "scanned"
    assert response.json()["warnings"]


def test_ocr_detection_estimates_original_font_size_and_color(tmp_path, monkeypatch):
    image_path = tmp_path / "ocr-style.png"
    image = Image.new("RGB", (500, 140), "white")
    draw = ImageDraw.Draw(image)
    font = _get_pil_font("Arial", 32, False, False)
    draw.text((30, 35), "Nishant", font=font, fill=(18, 46, 82))
    bbox = draw.textbbox((30, 35), "Nishant", font=font)
    image.save(image_path)

    monkeypatch.setattr(
        "app.services.detection_service.recognize_words",
        lambda _: [OcrWord("Nishant", 0.99, bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])],
    )
    detections = _ocr_detections("doc", image_path, 0, "Nishant", False, True)

    assert len(detections) == 1
    estimate = detections[0].font
    assert estimate.family is not None
    assert estimate.size is not None and estimate.size > 10
    assert estimate.color is not None and estimate.color != "#000000"
