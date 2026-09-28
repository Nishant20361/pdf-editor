"""Replaceable OCR provider interface with a Tesseract TSV implementation."""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class OcrUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


def is_ocr_available() -> bool:
    return shutil.which("tesseract") is not None or _rapidocr_available()


def _rapidocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def _rapidocr_engine():
    from rapidocr import RapidOCR
    return RapidOCR()


def _recognize_with_rapidocr(image_path: Path) -> list[OcrWord]:
    result = _rapidocr_engine()(str(image_path))
    if result.boxes is None or result.txts is None or result.scores is None:
        return []
    words: list[OcrWord] = []
    for points, text, confidence in zip(result.boxes, result.txts, result.scores):
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        left, top = int(min(xs)), int(min(ys))
        right, bottom = int(max(xs)), int(max(ys))
        if text.strip() and right > left and bottom > top:
            words.append(OcrWord(text=text.strip(), confidence=float(confidence), left=left, top=top, width=right - left, height=bottom - top))
    return words


def parse_tesseract_tsv(tsv: str) -> list[OcrWord]:
    words: list[OcrWord] = []
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf", "-1"))
            left = int(row.get("left", "0"))
            top = int(row.get("top", "0"))
            width = int(row.get("width", "0"))
            height = int(row.get("height", "0"))
        except (TypeError, ValueError):
            continue
        if confidence < 0 or width <= 0 or height <= 0:
            continue
        words.append(
            OcrWord(
                text=text,
                confidence=min(1.0, max(0.0, confidence / 100.0)),
                left=left,
                top=top,
                width=width,
                height=height,
            )
        )
    return words


def recognize_words(image_path: Path, language: str = "eng") -> list[OcrWord]:
    executable = shutil.which("tesseract")
    if executable is None and _rapidocr_available():
        return _recognize_with_rapidocr(image_path)
    if executable is None:
        raise OcrUnavailableError(
            "No OCR provider is available. Install RapidOCR or Tesseract to scan image text."
        )

    completed = subprocess.run(
        [executable, str(image_path), "stdout", "-l", language, "tsv"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or "Tesseract OCR failed."
        raise RuntimeError(message)
    return parse_tesseract_tsv(completed.stdout)
