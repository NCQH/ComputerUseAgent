"""Element detection for Set-of-Marks. OCR backend is injectable; pytesseract lazy."""
from __future__ import annotations


def _default_ocr(img):
    import pytesseract  # lazy; only needed for the real path
    return pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)


def detect_text_boxes(img, ocr=None, min_conf: int = 40):
    backend = ocr or _default_ocr
    data = backend(img)
    texts = data.get("text", [])
    boxes: list[tuple[int, int, int, int]] = []
    for i, text in enumerate(texts):
        if not (text or "").strip():
            continue
        try:
            conf = float(data["conf"][i])
            if conf < min_conf:
                continue
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        boxes.append((x, y, x + w, y + h))
    return boxes
