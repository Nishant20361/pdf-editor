"""Native PDF text replacement using PyMuPDF redaction + insertion.

For pages with native text, this avoids rasterisation by editing the PDF
layer directly.  For scanned/image pages, it renders at high DPI and
delegates to the image replacement pipeline.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF

from app.config import settings
from app.models.edit import EditRecord
from app.services.replacement_service import apply_edits_to_image

logger = logging.getLogger(__name__)

# Common base-14 PDF fonts available in every viewer
_PDF_BASE_FONTS = {
    "helvetica": "helv",
    "arial": "helv",
    "times": "tiro",
    "times new roman": "tiro",
    "courier": "cour",
    "courier new": "cour",
}


def _pdf_fontname(family: str, bold: bool = False, italic: bool = False) -> str:
    """Map a font family name to a PyMuPDF built-in font."""
    key = family.lower().strip()
    base = _PDF_BASE_FONTS.get(key)
    if base is None:
        if "times" in key or "serif" in key or "georgia" in key:
            base = "tiro"
        elif "courier" in key or "mono" in key:
            base = "cour"
        else:
            base = "helv"
    variants = {
        "helv": {(True, False): "hebo", (False, True): "heit", (True, True): "hebi"},
        "tiro": {(True, False): "tibo", (False, True): "tiit", (True, True): "tibi"},
        "cour": {(True, False): "cobo", (False, True): "coit", (True, True): "cobi"},
    }
    return variants.get(base, {}).get((bold, italic), base)


def _hex_to_fitz_color(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def apply_edits_to_native_pdf_page(
    page: fitz.Page,
    edits: list[EditRecord],
) -> None:
    """Apply edits directly on a native PDF page using redaction + text insertion.

    Modifies the page in-place.
    """
    pw = page.rect.width
    ph = page.rect.height

    for edit in edits:
        box = edit.current_box
        # Convert normalized coords to PDF points
        x0 = box.x * pw
        y0 = box.y * ph
        x1 = (box.x + box.width) * pw
        y1 = (box.y + box.height) * ph
        rect = fitz.Rect(x0, y0, x1, y1)

        # Add a redaction annotation to remove existing text
        page.add_redact_annot(rect, text="", fill=(1, 1, 1))

    # Apply all redactions in one pass
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Now insert replacement text
    for edit in edits:
        box = edit.current_box
        x0 = box.x * pw
        y0 = box.y * ph
        x1 = (box.x + box.width) * pw
        y1 = (box.y + box.height) * ph
        rect = fitz.Rect(x0, y0, x1, y1)

        fontname = _pdf_fontname(edit.font_family, edit.font_weight == "bold", edit.font_style == "italic")
        color = _hex_to_fitz_color(edit.font_color)

        # Keep the original baseline/size. insert_textbox needs extra line
        # height and therefore used to shrink even short replacements. A
        # baseline insertion matches the tight span box much more faithfully.
        font_size = edit.font_size
        text_width = fitz.get_text_length(edit.replacement_text, fontname=fontname, fontsize=font_size)
        while text_width > rect.width * 1.08 and font_size > 5:
            font_size -= 0.5
            text_width = fitz.get_text_length(edit.replacement_text, fontname=fontname, fontsize=font_size)

        text_x = rect.x0
        if edit.alignment == "center":
            text_x += max(0.0, (rect.width - text_width) / 2)
        elif edit.alignment == "right":
            text_x += max(0.0, rect.width - text_width)
        baseline = rect.y1 - max(0.5, font_size * 0.22)
        page.insert_text(
            fitz.Point(text_x, baseline),
            edit.replacement_text,
            fontname=fontname,
            fontsize=font_size,
            color=color,
        )


def apply_edits_to_scanned_pdf_page(
    page: fitz.Page,
    edits: list[EditRecord],
    dpi: int = 300,
) -> bytes:
    """Render a scanned PDF page, apply image edits, return PNG bytes."""
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_bytes = pix.tobytes("png")
    return apply_edits_to_image(img_bytes, edits, font_scale=dpi / 72)


def render_pdf_with_edits(
    file_path: Path,
    edits_by_page: dict[int, list[EditRecord]],
    page_types: dict[int, str],
    dpi: int | None = None,
) -> dict[int, bytes]:
    """Render PDF pages with edits applied.

    For native pages: edits the PDF layer and re-renders.
    For scanned pages: renders at high DPI and applies image pipeline.

    Returns a dict of page_number -> PNG bytes.
    """
    render_dpi = dpi or settings.PREVIEW_DPI
    results: dict[int, bytes] = {}

    doc = fitz.open(str(file_path))
    try:
        for page_num, edits in edits_by_page.items():
            if page_num < 0 or page_num >= doc.page_count:
                continue
            page = doc[page_num]
            content_type = page_types.get(page_num, "scanned")

            if content_type == "native":
                # Work on a copy to preserve original
                temp_doc = fitz.open(str(file_path))
                temp_page = temp_doc[page_num]
                apply_edits_to_native_pdf_page(temp_page, edits)
                zoom = render_dpi / 72
                pix = temp_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                results[page_num] = pix.tobytes("png")
                temp_doc.close()
            else:
                results[page_num] = apply_edits_to_scanned_pdf_page(page, edits, render_dpi)

    finally:
        doc.close()

    return results


def render_single_page_preview(
    file_path: Path,
    page_number: int,
    edits: list[EditRecord],
    content_type: str,
    dpi: int | None = None,
) -> bytes:
    """Render a single page with edits applied, return PNG bytes."""
    render_dpi = dpi or settings.PREVIEW_DPI
    doc = fitz.open(str(file_path))
    try:
        if page_number < 0 or page_number >= doc.page_count:
            raise ValueError(f"Page {page_number} is out of range.")
        page = doc[page_number]

        has_native_text = bool(page.get_text().strip())
        has_images = bool(page.get_images(full=True))
        actual_content_type = "native" if has_native_text and not has_images else "scanned"

        if actual_content_type == "native" and edits:
            temp_doc = fitz.open(str(file_path))
            temp_page = temp_doc[page_number]
            apply_edits_to_native_pdf_page(temp_page, edits)
            zoom = render_dpi / 72
            pix = temp_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            result = pix.tobytes("png")
            temp_doc.close()
            return result
        elif edits:
            return apply_edits_to_scanned_pdf_page(page, edits, render_dpi)
        else:
            zoom = render_dpi / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("png")
    finally:
        doc.close()
