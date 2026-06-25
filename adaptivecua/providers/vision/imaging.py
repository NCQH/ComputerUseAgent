"""Pure image helpers for the generic vision provider. Pillow is lazy-imported."""
from __future__ import annotations

import base64
import io

_MARK_COLOR = (0, 128, 255)
_GRID_COLOR = (255, 0, 0)


def decode(b64: str):
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def encode(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def overlay_grid(img, cols: int = 12, rows: int = 8):
    from PIL import ImageDraw
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    cw, ch = w / cols, h / rows
    centers: dict[int, tuple[int, int]] = {}
    n = 0
    for r in range(rows):
        for c in range(cols):
            x0, y0 = int(c * cw), int(r * ch)
            x1, y1 = int(x0 + cw), int(y0 + ch)
            centers[n] = (int(x0 + cw / 2), int(y0 + ch / 2))
            draw.rectangle([x0, y0, x1, y1], outline=_GRID_COLOR)
            draw.text((x0 + 2, y0 + 2), str(n), fill=_GRID_COLOR)
            n += 1
    return out, centers


def annotate_marks(img, boxes):
    from PIL import ImageDraw
    out = img.copy()
    draw = ImageDraw.Draw(out)
    marks: dict[int, tuple[int, int]] = {}
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        marks[i] = (int((x0 + x1) / 2), int((y0 + y1) / 2))
        draw.rectangle([x0, y0, x1, y1], outline=_MARK_COLOR)
        draw.text((x0, max(0, y0 - 10)), str(i), fill=_MARK_COLOR)
    return out, marks


def crop_region(img, box, zoom: int = 2):
    x0, y0, x1, y1 = box
    crop = img.crop((x0, y0, x1, y1))
    w, h = crop.size
    return crop.resize((max(1, w * zoom), max(1, h * zoom)))
