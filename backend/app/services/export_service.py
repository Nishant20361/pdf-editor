"""Export service — renders edited documents to downloadable files.

Reuses the same rendering pipeline as preview so output matches the After view.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

from app.config import settings
from app.models.document import DocumentMetadata, DocumentType
from app.models.edit import EditRecord, edit_store
from app.models.export import (
    ExportFormat,
    ExportJob,
    ExportMode,
    ExportStatus,
    PageSelection,
    export_store,
    parse_page_range,
)
from app.services.file_service import get_file_path
from app.services.image_service import get_original_image_bytes
from app.services.pdf_replacement_service import (
    apply_edits_to_native_pdf_page,
    apply_edits_to_scanned_pdf_page,
)
from app.services.replacement_service import apply_edits_to_image
from app.utils.security import sanitize_filename, validate_path_safety

logger = logging.getLogger(__name__)

EXPORT_DIR_NAME = "exports"
_MIME_MAP = {
    ExportFormat.PNG: "image/png",
    ExportFormat.JPEG: "image/jpeg",
    ExportFormat.WEBP: "image/webp",
    ExportFormat.PDF: "application/pdf",
    ExportFormat.PDF_FLATTENED: "application/pdf",
    ExportFormat.ZIP_IMAGES: "application/zip",
}
_EXT_MAP = {
    ExportFormat.PNG: ".png",
    ExportFormat.JPEG: ".jpg",
    ExportFormat.WEBP: ".webp",
    ExportFormat.PDF: ".pdf",
    ExportFormat.PDF_FLATTENED: ".pdf",
    ExportFormat.ZIP_IMAGES: ".zip",
}


def _ensure_export_dir() -> Path:
    d = settings.UPLOAD_DIR / EXPORT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_output_filename(original: str, ext: str) -> str:
    base = Path(original).stem
    base = sanitize_filename(base)
    if not base or base == "unnamed":
        base = "export"
    return f"{base}_edited{ext}"


def _get_page_content_type(page: fitz.Page) -> str:
    native_text = page.get_text().strip()
    has_images = bool(page.get_images(full=True))
    if native_text and not has_images:
        return "native"
    elif native_text and has_images:
        return "mixed"
    return "scanned"


def _resolve_pages(
    doc: DocumentMetadata,
    selection: PageSelection,
    current_page: int,
    custom_spec: Optional[str],
) -> list[int]:
    """Resolve the list of 0-indexed pages to export."""
    if selection == PageSelection.ALL:
        return list(range(doc.page_count))
    elif selection == PageSelection.CURRENT:
        if current_page < doc.page_count:
            return [current_page]
        return [0]
    elif selection == PageSelection.EDITED:
        edits = edit_store.list_edits(doc.id)
        edited = sorted({e.page_number for e in edits if e.page_number < doc.page_count})
        return edited if edited else list(range(doc.page_count))
    elif selection == PageSelection.CUSTOM and custom_spec:
        return parse_page_range(custom_spec, doc.page_count)
    return list(range(doc.page_count))


def _render_image_export(
    doc: DocumentMetadata,
    file_path: Path,
    fmt: ExportFormat,
    quality: int,
    edits: list[EditRecord],
    output_width: Optional[int],
    output_height: Optional[int],
    preserve_dimensions: bool,
) -> tuple[bytes, str]:
    """Export a single image with edits applied."""
    image_bytes = get_original_image_bytes(file_path)
    if edits:
        image_bytes = apply_edits_to_image(image_bytes, edits)

    img = Image.open(io.BytesIO(image_bytes))

    # Resize if requested
    if not preserve_dimensions and (output_width or output_height):
        w = output_width or img.width
        h = output_height or img.height
        img = img.resize((w, h), Image.LANCZOS)

    buf = io.BytesIO()
    if fmt == ExportFormat.PNG:
        if img.mode == "RGBA":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.convert("RGB").save(buf, format="PNG", optimize=True)
        mime = "image/png"
    elif fmt == ExportFormat.JPEG:
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        mime = "image/jpeg"
    elif fmt == ExportFormat.WEBP:
        img.convert("RGB").save(buf, format="WEBP", quality=quality)
        mime = "image/webp"
    else:
        img.convert("RGB").save(buf, format="PNG", optimize=True)
        mime = "image/png"

    return buf.getvalue(), mime


def _export_pdf_preserve(
    file_path: Path,
    pages: list[int],
    edits_by_page: dict[int, list[EditRecord]],
    job: ExportJob,
) -> bytes:
    """Export PDF preserving vector content — native redaction/insertion."""
    doc = fitz.open(str(file_path))
    try:
        for i, page_num in enumerate(pages):
            if page_num >= doc.page_count:
                continue
            edits = edits_by_page.get(page_num, [])
            if edits:
                page = doc[page_num]
                content_type = _get_page_content_type(page)
                if content_type == "native":
                    apply_edits_to_native_pdf_page(page, edits)
                else:
                    # For scanned pages, render and replace the page image
                    png_bytes = apply_edits_to_scanned_pdf_page(page, edits, 200)
                    # Insert rendered image as new page content
                    rect = page.rect
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()
                    page.insert_image(rect, stream=png_bytes)
            job.progress = ((i + 1) / len(pages)) * 100
            export_store.update(job)

        # Remove pages not in selection (in reverse order)
        if len(pages) < doc.page_count:
            all_pages = set(range(doc.page_count))
            to_remove = sorted(all_pages - set(pages), reverse=True)
            for p in to_remove:
                doc.delete_page(p)

        buf = io.BytesIO()
        doc.save(buf, garbage=4, deflate=True, clean=True)
        return buf.getvalue()
    finally:
        doc.close()


def _export_pdf_flattened(
    file_path: Path,
    pages: list[int],
    edits_by_page: dict[int, list[EditRecord]],
    quality: int,
    job: ExportJob,
) -> bytes:
    """Export a flattened PDF — every page rendered as image."""
    src = fitz.open(str(file_path))
    out = fitz.open()
    try:
        for i, page_num in enumerate(pages):
            if page_num >= src.page_count:
                continue
            src_page = src[page_num]
            edits = edits_by_page.get(page_num, [])

            # Render the page
            zoom = 200 / 72
            mat = fitz.Matrix(zoom, zoom)
            if edits:
                content_type = _get_page_content_type(src_page)
                if content_type == "native":
                    temp_doc = fitz.open(str(file_path))
                    temp_page = temp_doc[page_num]
                    apply_edits_to_native_pdf_page(temp_page, edits)
                    pix = temp_page.get_pixmap(matrix=mat, alpha=False)
                    png_bytes = pix.tobytes("png")
                    temp_doc.close()
                else:
                    png_bytes = apply_edits_to_scanned_pdf_page(src_page, edits, 200)
            else:
                pix = src_page.get_pixmap(matrix=mat, alpha=False)
                png_bytes = pix.tobytes("png")

            # Create output page with same dimensions
            new_page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
            new_page.insert_image(new_page.rect, stream=png_bytes)

            job.progress = ((i + 1) / len(pages)) * 100
            export_store.update(job)

        buf = io.BytesIO()
        out.save(buf, garbage=4, deflate=True)
        return buf.getvalue()
    finally:
        src.close()
        out.close()


def _export_image_pages(
    file_path: Path,
    pages: list[int],
    edits_by_page: dict[int, list[EditRecord]],
    img_format: str,
    quality: int,
    job: ExportJob,
) -> list[tuple[str, bytes]]:
    """Render pages as individual images. Returns list of (filename, bytes)."""
    results = []
    ext = ".png" if img_format == "png" else ".jpg"
    src = fitz.open(str(file_path))
    try:
        for i, page_num in enumerate(pages):
            if page_num >= src.page_count:
                continue
            page = src[page_num]
            edits = edits_by_page.get(page_num, [])
            zoom = 200 / 72
            mat = fitz.Matrix(zoom, zoom)

            if edits:
                content_type = _get_page_content_type(page)
                if content_type == "native":
                    temp_doc = fitz.open(str(file_path))
                    temp_page = temp_doc[page_num]
                    apply_edits_to_native_pdf_page(temp_page, edits)
                    pix = temp_page.get_pixmap(matrix=mat, alpha=False)
                    png_bytes = pix.tobytes("png")
                    temp_doc.close()
                else:
                    png_bytes = apply_edits_to_scanned_pdf_page(page, edits, 200)
            else:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                png_bytes = pix.tobytes("png")

            # Convert to target format
            img = Image.open(io.BytesIO(png_bytes))
            buf = io.BytesIO()
            if img_format == "jpeg":
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
            else:
                img.save(buf, format="PNG", optimize=True)

            results.append((f"page_{page_num + 1}{ext}", buf.getvalue()))

            job.progress = ((i + 1) / len(pages)) * 100
            export_store.update(job)

        return results
    finally:
        src.close()


def _create_zip(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buf.getvalue()


def run_export(doc: DocumentMetadata, job: ExportJob, request) -> None:
    """Execute an export job. Updates job status in-place."""
    try:
        job.status = ExportStatus.PROCESSING
        export_store.update(job)

        file_path = get_file_path(doc)
        all_edits = edit_store.list_edits(doc.id)

        # Resolve pages
        pages = _resolve_pages(doc, request.page_selection, request.current_page, request.custom_pages)
        if not pages:
            pages = list(range(doc.page_count))

        job.page_count = len(pages)

        # Group edits by page
        edits_by_page: dict[int, list[EditRecord]] = {}
        for edit in all_edits:
            edits_by_page.setdefault(edit.page_number, []).append(edit)

        # Generate output filename
        ext = _EXT_MAP.get(request.output_format, ".pdf")
        if request.filename:
            safe = sanitize_filename(request.filename)
            if not safe.endswith(ext):
                safe = safe.rsplit(".", 1)[0] + ext if "." in safe else safe + ext
            job.filename = safe
        else:
            job.filename = _safe_output_filename(doc.original_filename, ext)

        job.mime_type = _MIME_MAP.get(request.output_format, "application/octet-stream")

        # ---- Image document ----
        if doc.document_type == DocumentType.IMAGE:
            page_edits = edits_by_page.get(0, [])
            data, mime = _render_image_export(
                doc, file_path, request.output_format,
                request.quality, page_edits,
                request.output_width, request.output_height,
                request.preserve_dimensions,
            )
            job.mime_type = mime
            result_bytes = data
            job.progress = 100

        # ---- PDF document ----
        elif doc.document_type == DocumentType.PDF:
            fmt = request.output_format

            if fmt in (ExportFormat.PNG, ExportFormat.JPEG, ExportFormat.WEBP):
                # Single-page image export (first selected page)
                target_page = pages[0] if pages else 0
                page_edits = edits_by_page.get(target_page, [])
                # Render page as image
                pdf = fitz.open(str(file_path))
                try:
                    page = pdf[target_page]
                    ct = _get_page_content_type(page)
                    zoom = 200 / 72
                    if page_edits and ct == "native":
                        temp = fitz.open(str(file_path))
                        tp = temp[target_page]
                        apply_edits_to_native_pdf_page(tp, page_edits)
                        pix = tp.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        png_bytes = pix.tobytes("png")
                        temp.close()
                    elif page_edits:
                        png_bytes = apply_edits_to_scanned_pdf_page(page, page_edits, 200)
                    else:
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        png_bytes = pix.tobytes("png")
                finally:
                    pdf.close()

                img = Image.open(io.BytesIO(png_bytes))
                if not request.preserve_dimensions and (request.output_width or request.output_height):
                    w = request.output_width or img.width
                    h = request.output_height or img.height
                    img = img.resize((w, h), Image.LANCZOS)

                buf = io.BytesIO()
                if fmt == ExportFormat.PNG:
                    img.save(buf, format="PNG", optimize=True)
                elif fmt == ExportFormat.JPEG:
                    img.convert("RGB").save(buf, format="JPEG", quality=request.quality)
                else:
                    img.convert("RGB").save(buf, format="WEBP", quality=request.quality)
                result_bytes = buf.getvalue()
                job.progress = 100

            elif fmt == ExportFormat.PDF:
                result_bytes = _export_pdf_preserve(file_path, pages, edits_by_page, job)

            elif fmt == ExportFormat.PDF_FLATTENED:
                result_bytes = _export_pdf_flattened(file_path, pages, edits_by_page, request.quality, job)

            elif fmt == ExportFormat.ZIP_IMAGES:
                image_files = _export_image_pages(
                    file_path, pages, edits_by_page,
                    request.image_format_for_zip, request.quality, job,
                )
                result_bytes = _create_zip(image_files)

            else:
                raise ValueError(f"Unsupported format: {fmt}")
        else:
            raise ValueError("Unknown document type")

        # Save result
        export_dir = _ensure_export_dir()
        stored_name = f"{job.id}{ext}"
        out_path = export_dir / stored_name
        validated = validate_path_safety(out_path)
        validated.write_bytes(result_bytes)

        job.stored_filename = stored_name
        job.file_size = len(result_bytes)
        job.progress = 100
        job.status = ExportStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        export_store.update(job)
        logger.info("Export completed: %s (%d bytes)", job.id, job.file_size)

    except Exception as exc:
        logger.error("Export failed for job %s: %s", job.id, exc, exc_info=True)
        job.status = ExportStatus.FAILED
        job.error = str(exc)[:500]
        job.completed_at = datetime.now(timezone.utc)
        export_store.update(job)


def get_export_file_path(job: ExportJob) -> Path | None:
    """Return the full path to an export file, or None."""
    if not job.stored_filename:
        return None
    p = settings.UPLOAD_DIR / EXPORT_DIR_NAME / job.stored_filename
    try:
        validated = validate_path_safety(p)
        return validated if validated.exists() else None
    except ValueError:
        return None


def cleanup_export(job: ExportJob) -> None:
    """Delete the export file from disk."""
    path = get_export_file_path(job)
    if path and path.exists():
        try:
            path.unlink()
        except OSError:
            pass
