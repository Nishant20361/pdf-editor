"""Text extraction and normalized search across images and PDF pages."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import fitz
import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.models.detection import (
    DetectionSource,
    FontEstimate,
    NormalizedBoundingBox,
    PageAnalysis,
    PageContentType,
    TextDetection,
)
from app.models.document import DocumentMetadata, DocumentType
from app.services.ocr_service import OcrUnavailableError, is_ocr_available, recognize_words
from app.services.replacement_service import _get_pil_font


_OCR_FONT_CANDIDATES = ("Arial", "Helvetica", "Times New Roman", "Courier New", "Georgia", "Verdana", "Impact")


def _matches(text: str, query: str, case_sensitive: bool, exact_match: bool) -> bool:
    candidate = text if case_sensitive else text.casefold()
    needle = query if case_sensitive else query.casefold()
    return candidate == needle if exact_match else needle in candidate


def _box(x0: float, y0: float, x1: float, y1: float, width: float, height: float) -> NormalizedBoundingBox:
    x = max(0.0, min(1.0, x0 / width))
    y = max(0.0, min(1.0, y0 / height))
    right = max(x, min(1.0, x1 / width))
    bottom = max(y, min(1.0, y1 / height))
    return NormalizedBoundingBox(x=x, y=y, width=max(0.000001, right - x), height=max(0.000001, bottom - y))


def _rgb_hex(color: int) -> str:
    return f"#{color & 0xFFFFFF:06x}"


def _ocr_font_estimate(
    image: Image.Image,
    text: str,
    left: int,
    top: int,
    width: int,
    height: int,
    points_per_pixel: float,
) -> FontEstimate:
    """Estimate visual text style from an OCR word crop.

    OCR engines return geometry but not typography. We recover the foreground
    colour, point size and the closest locally available common font by
    comparing rendered glyph masks with the pixels in the source crop.
    """
    rgb = np.asarray(image.convert("RGB"))
    image_h, image_w = rgb.shape[:2]
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(image_w, left + width), min(image_h, top + height)
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return FontEstimate(family="Arial", size=max(4.0, height * 1.25 * points_per_pixel), color="#000000")

    border = np.concatenate((crop[0], crop[-1], crop[:, 0], crop[:, -1]), axis=0).astype(np.float32)
    background = np.median(border, axis=0)
    distance = np.linalg.norm(crop.astype(np.float32) - background, axis=2)
    threshold = max(24.0, float(np.percentile(distance, 70)))
    mask = distance >= threshold
    if int(mask.sum()) < max(3, crop.shape[0] * crop.shape[1] // 100):
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        mask = dark > 0

    foreground = crop[mask]
    colour = np.median(foreground, axis=0).astype(int) if foreground.size else np.array([0, 0, 0])
    colour_hex = f"#{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}"

    target = (mask.astype(np.uint8) * 255)
    ys, xs = np.where(target > 0)
    if xs.size:
        target = target[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # OCR boxes usually cover cap-height, which is about 75-80% of the font's em size.
    pixel_size = max(6.0, height * 1.28)
    point_size = round(max(4.0, pixel_size * points_per_pixel) * 2) / 2
    best = (float("inf"), "Arial", False, False)
    for family in _OCR_FONT_CANDIDATES:
        for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
            font = _get_pil_font(family, pixel_size, bold, italic)
            probe = Image.new("L", (max(32, width * 3), max(32, height * 3)), 0)
            draw = ImageDraw.Draw(probe)
            box = draw.textbbox((2, 2), text, font=font)
            draw.text((2 - box[0], 2 - box[1]), text, font=font, fill=255)
            array = np.asarray(probe)
            py, px = np.where(array > 32)
            if not px.size or target.size == 0:
                continue
            rendered = array[py.min():py.max() + 1, px.min():px.max() + 1]
            aspect_error = abs((rendered.shape[1] / max(1, rendered.shape[0])) - (target.shape[1] / max(1, target.shape[0])))
            fitted = cv2.resize(rendered, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_AREA)
            binary = fitted > 80
            target_binary = target > 0
            union = np.logical_or(binary, target_binary).sum()
            iou = np.logical_and(binary, target_binary).sum() / max(1, union)
            score = (1.0 - iou) + min(2.0, aspect_error) * 0.2
            if score < best[0]:
                best = (score, family, bold, italic)

    return FontEstimate(family=best[1], size=point_size, color=colour_hex, bold=best[2], italic=best[3])


def _native_pdf_detections(
    document_id: str,
    page: fitz.Page,
    query: str,
    case_sensitive: bool,
    exact_match: bool,
) -> list[TextDetection]:
    results: list[TextDetection] = []
    page_width, page_height = page.rect.width, page.rect.height
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                if not text or not _matches(text, query, case_sensitive, exact_match):
                    continue
                x0, y0, x1, y1 = span["bbox"]
                flags = int(span.get("flags", 0))
                results.append(
                    TextDetection(
                        id=uuid.uuid4().hex,
                        document_id=document_id,
                        page_number=page.number,
                        text=text,
                        bounding_box=_box(x0, y0, x1, y1, page_width, page_height),
                        confidence=1.0,
                        source=DetectionSource.NATIVE_PDF,
                        font=FontEstimate(
                            family=span.get("font"),
                            size=float(span.get("size", 0)) or None,
                            color=_rgb_hex(int(span.get("color", 0))),
                            bold=bool(flags & 16),
                            italic=bool(flags & 2),
                        ),
                    )
                )
    return results


def _ocr_detections(
    document_id: str,
    image_path: Path,
    page_number: int,
    query: str,
    case_sensitive: bool,
    exact_match: bool,
    points_per_pixel: float = 1.0,
) -> list[TextDetection]:
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        results: list[TextDetection] = []
        for word in recognize_words(image_path):
            if not _matches(word.text, query, case_sensitive, exact_match):
                continue
            results.append(TextDetection(
                id=uuid.uuid4().hex,
                document_id=document_id,
                page_number=page_number,
                text=word.text,
                bounding_box=_box(
                    word.left,
                    word.top,
                    word.left + word.width,
                    word.top + word.height,
                    width,
                    height,
                ),
                confidence=word.confidence,
                source=DetectionSource.OCR,
                font=_ocr_font_estimate(
                    image, word.text, word.left, word.top, word.width, word.height, points_per_pixel
                ),
            ))
    return results


def detect_text(
    document: DocumentMetadata,
    file_path: Path,
    query: str,
    case_sensitive: bool,
    exact_match: bool,
    page_number: int | None,
) -> tuple[list[PageAnalysis], list[TextDetection], list[str]]:
    warnings: list[str] = []
    pages: list[PageAnalysis] = []
    detections: list[TextDetection] = []

    if document.document_type == DocumentType.IMAGE:
        with Image.open(file_path) as image:
            width, height = image.size
        pages.append(PageAnalysis(page_number=0, content_type=PageContentType.SCANNED, width=width, height=height))
        if not is_ocr_available():
            warnings.append("Tesseract OCR is not installed. Install it to scan image text.")
            return pages, detections, warnings
        try:
            detections.extend(_ocr_detections(document.id, file_path, 0, query, case_sensitive, exact_match))
        except OcrUnavailableError as exc:
            warnings.append(str(exc))
        return pages, detections, warnings

    pdf = fitz.open(str(file_path))
    try:
        indices = [page_number] if page_number is not None else list(range(pdf.page_count))
        for index in indices:
            if index < 0 or index >= pdf.page_count:
                raise ValueError(f"Page {index} is out of range.")
            page = pdf[index]
            native_text = page.get_text().strip()
            has_native = bool(native_text)
            has_images = bool(page.get_images(full=True))
            content_type = (
                PageContentType.MIXED
                if has_native and has_images
                else PageContentType.NATIVE
                if has_native
                else PageContentType.SCANNED
            )
            pages.append(
                PageAnalysis(
                    page_number=index,
                    content_type=content_type,
                    width=page.rect.width,
                    height=page.rect.height,
                )
            )
            if has_native:
                detections.extend(_native_pdf_detections(document.id, page, query, case_sensitive, exact_match))

            if not has_native or has_images:
                if not is_ocr_available():
                    warnings.append(f"Page {index + 1}: OCR is unavailable, so image text was not searched.")
                    continue
                with tempfile.TemporaryDirectory() as temp_dir:
                    image_path = Path(temp_dir) / f"page-{index}.png"
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pixmap.save(str(image_path))
                    detections.extend(
                        _ocr_detections(
                            document.id, image_path, index, query, case_sensitive, exact_match,
                            points_per_pixel=0.5,
                        )
                    )
    finally:
        pdf.close()
    return pages, detections, list(dict.fromkeys(warnings))
