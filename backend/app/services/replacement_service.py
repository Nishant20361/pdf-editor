"""Text replacement engine for images and scanned PDF pages.

Handles background cleanup (solid fill, inpainting, blur) and
antialiased text rendering with style matching.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.models.edit import BackgroundCleanupMethod, EditRecord

logger = logging.getLogger(__name__)

# Font paths to search on common OSes
_FONT_SEARCH = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Times.ttc",
    "/System/Library/Fonts/Courier.dfont",
    "/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial Italic.ttf",
    "/Library/Fonts/Arial Bold Italic.ttf",
    "/Library/Fonts/Georgia.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "/Library/Fonts/Verdana.ttf",
    "/Library/Fonts/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _find_font(family: str, bold: bool = False, italic: bool = False) -> Optional[str]:
    """Try to locate a font file on the filesystem."""
    # Build target filename patterns
    style = ""
    if bold and italic:
        style = "Bold Italic"
    elif bold:
        style = "Bold"
    elif italic:
        style = "Italic"

    patterns = []
    if family:
        base = family.split(",")[0].strip()
        # PDF font names often include subset prefixes and PostScript suffixes.
        if "+" in base:
            base = base.split("+", 1)[1]
        for suffix in ("-BoldItalic", "-Bold", "-Italic", "PSMT", "MT"):
            base = base.replace(suffix, "")
        if style:
            patterns.append(f"{base} {style}.ttf")
            patterns.append(f"{base}{style.replace(' ', '')}.ttf")
        patterns.append(f"{base}.ttf")
        patterns.append(f"{base}.ttc")

    # Check the most specific style pattern across every path before falling
    # back to the regular face. Otherwise Arial.ttf wins before Arial Bold.ttf.
    existing = [Path(path_str) for path_str in _FONT_SEARCH if Path(path_str).exists()]
    for pattern in patterns:
        for path in existing:
            if pattern.lower() in path.name.lower():
                return str(path)

    # Last resort: return first available font
    for path_str in _FONT_SEARCH:
        if Path(path_str).exists():
            return path_str
    return None


def _get_pil_font(family: str, size: float, bold: bool, italic: bool) -> ImageFont.FreeTypeFont:
    """Get a PIL font, falling back gracefully."""
    font_path = _find_font(family, bold, italic)
    try:
        if font_path:
            return ImageFont.truetype(font_path, size=int(round(size)))
        return ImageFont.truetype("Arial", size=int(round(size)))
    except (OSError, IOError):
        try:
            return ImageFont.load_default(size=int(round(size)))
        except TypeError:
            return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #rrggbb to (r, g, b)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    r, g, b = _hex_to_rgb(hex_color)
    return (b, g, r)


def _sample_background_color(img_np: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[int, int, int]:
    """Sample the dominant background color around a bounding box."""
    ih, iw = img_np.shape[:2]
    pad = max(4, min(w, h) // 4)

    regions = []
    # Top edge
    if y > pad:
        regions.append(img_np[max(0, y - pad):y, x:x + w])
    # Bottom edge
    if y + h + pad < ih:
        regions.append(img_np[y + h:min(ih, y + h + pad), x:x + w])
    # Left edge
    if x > pad:
        regions.append(img_np[y:y + h, max(0, x - pad):x])
    # Right edge
    if x + w + pad < iw:
        regions.append(img_np[y:y + h, x + w:min(iw, x + w + pad)])

    if not regions:
        return (255, 255, 255)

    combined = np.concatenate([r.reshape(-1, 3) for r in regions if r.size > 0], axis=0)
    if combined.size == 0:
        return (255, 255, 255)

    median = np.median(combined, axis=0).astype(int)
    return (int(median[0]), int(median[1]), int(median[2]))


def cleanup_background(
    img_np: np.ndarray,
    x: int, y: int, w: int, h: int,
    method: BackgroundCleanupMethod,
    manual_color: Optional[str] = None,
) -> np.ndarray:
    """Remove original text from the bounding box region.

    Returns a new image array with the region cleaned.
    """
    result = img_np.copy()
    ih, iw = result.shape[:2]

    # Clamp coordinates
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(iw, x + w)
    y2 = min(ih, y + h)

    if x2 <= x1 or y2 <= y1:
        return result

    if method == BackgroundCleanupMethod.MANUAL_COLOR and manual_color:
        bgr = _hex_to_bgr(manual_color)
        result[y1:y2, x1:x2] = bgr

    elif method == BackgroundCleanupMethod.SOLID:
        bg_color = _sample_background_color(result, x1, y1, x2 - x1, y2 - y1)
        result[y1:y2, x1:x2] = bg_color

    elif method == BackgroundCleanupMethod.INPAINT:
        # Create a mask for the text region
        mask = np.zeros(result.shape[:2], dtype=np.uint8)
        pad = max(2, min(w, h) // 8)
        mx1 = max(0, x1 - pad)
        my1 = max(0, y1 - pad)
        mx2 = min(iw, x2 + pad)
        my2 = min(ih, y2 + pad)
        mask[my1:my2, mx1:mx2] = 255
        result = cv2.inpaint(result, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)

    elif method == BackgroundCleanupMethod.BLUR:
        region = result[y1:y2, x1:x2]
        ksize = max(5, (min(w, h) // 3) | 1)  # Ensure odd
        blurred = cv2.GaussianBlur(region, (ksize, ksize), 0)
        result[y1:y2, x1:x2] = blurred

    return result


def render_replacement_text(
    img_pil: Image.Image,
    edit: EditRecord,
    img_width: int,
    img_height: int,
    font_scale: float = 1.0,
) -> Image.Image:
    """Render replacement text onto a PIL Image at the correct position."""
    result = img_pil.copy()
    if result.mode != "RGBA":
        result = result.convert("RGBA")

    box = edit.current_box
    px = int(box.x * img_width)
    py = int(box.y * img_height)
    pw = int(box.width * img_width)
    ph = int(box.height * img_height)

    if pw <= 0 or ph <= 0:
        return result

    is_bold = edit.font_weight == "bold"
    is_italic = edit.font_style == "italic"

    # Auto-fit: try to fit text in box by reducing font size if needed
    font_size = edit.font_size * font_scale
    font = _get_pil_font(edit.font_family, font_size, is_bold, is_italic)

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    text_bbox = draw.textbbox((0, 0), edit.replacement_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    # Auto-shrink to fit (but not below 6pt)
    while text_w > pw * 1.1 and font_size > 6:
        font_size -= 0.5
        font = _get_pil_font(edit.font_family, font_size, is_bold, is_italic)
        text_bbox = draw.textbbox((0, 0), edit.replacement_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

    # Create text overlay with transparency
    overlay = Image.new("RGBA", (max(pw, text_w + 4), max(ph, text_h + 4)), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Calculate position based on alignment
    text_x = 0
    if edit.alignment == "center":
        text_x = max(0, (overlay.width - text_w) // 2)
    elif edit.alignment == "right":
        text_x = max(0, overlay.width - text_w)

    # Vertical centering
    # textbbox may start below zero/above the drawing origin depending on the
    # font ascender. Compensating for it keeps the new baseline aligned with
    # the original OCR box instead of making replacement text look lower.
    text_y = max(0, (overlay.height - text_h) // 2) - text_bbox[1]

    text_color = _hex_to_rgb(edit.font_color)

    # Draw with antialiasing (PIL does this by default for truetype)
    draw_overlay.text(
        (text_x, text_y),
        edit.replacement_text,
        font=font,
        fill=(*text_color, 255),
    )

    # Handle rotation
    if abs(edit.rotation) > 0.5:
        overlay = overlay.rotate(-edit.rotation, expand=True, resample=Image.BICUBIC)

    # Paste onto result
    result.paste(overlay, (px, py), overlay)

    return result


def apply_edits_to_image(
    image_bytes: bytes,
    edits: list[EditRecord],
    font_scale: float = 1.0,
) -> bytes:
    """Apply all edits to an image, returning PNG bytes.

    Pipeline:
    1. For each edit: cleanup background in the bounding box
    2. For each edit: render replacement text
    """
    img_pil = Image.open(BytesIO(image_bytes))
    if img_pil.mode == "RGBA":
        # Flatten alpha for OpenCV processing
        background = Image.new("RGB", img_pil.size, (255, 255, 255))
        background.paste(img_pil, mask=img_pil.split()[3])
        img_pil = background
    elif img_pil.mode != "RGB":
        img_pil = img_pil.convert("RGB")

    img_width, img_height = img_pil.size
    img_np = np.array(img_pil)
    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    # Step 1: Clean up backgrounds
    for edit in edits:
        box = edit.current_box
        px = int(box.x * img_width)
        py = int(box.y * img_height)
        pw = int(box.width * img_width)
        ph = int(box.height * img_height)
        img_np = cleanup_background(img_np, px, py, pw, ph, edit.bg_cleanup, edit.bg_color)

    # Convert back to PIL for text rendering
    img_np_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_np_rgb)

    # Step 2: Render replacement texts
    for edit in edits:
        img_pil = render_replacement_text(img_pil, edit, img_width, img_height, font_scale=font_scale)

    # Convert back to RGB if needed
    if img_pil.mode == "RGBA":
        background = Image.new("RGB", img_pil.size, (255, 255, 255))
        background.paste(img_pil, mask=img_pil.split()[3])
        img_pil = background

    buf = BytesIO()
    img_pil.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
