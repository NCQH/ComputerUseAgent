import pytest
pytest.importorskip("PIL")

from PIL import Image
from cua.providers.vision.imaging import decode, encode, overlay_grid, annotate_marks, crop_region


def _img(w=120, h=80):
    return Image.new("RGB", (w, h), (255, 255, 255))


def test_encode_decode_roundtrip():
    img = _img()
    b64 = encode(img)
    back = decode(b64)
    assert back.size == (120, 80)


def test_overlay_grid_centers_count_and_position():
    img = _img(120, 80)
    out, centers = overlay_grid(img, cols=4, rows=2)
    assert out.size == (120, 80)
    assert len(centers) == 8           # 4 * 2 cells
    # cell 0 centre is in the top-left cell (within first 30x40 block)
    cx, cy = centers[0]
    assert 0 < cx < 30 and 0 < cy < 40


def test_annotate_marks_returns_box_centers():
    img = _img(100, 100)
    out, marks = annotate_marks(img, [(10, 10, 30, 30), (50, 60, 70, 80)])
    assert out.size == (100, 100)
    assert marks[0] == (20, 20)
    assert marks[1] == (60, 70)


def test_crop_region_zooms():
    img = _img(100, 100)
    crop = crop_region(img, (10, 10, 30, 20), zoom=3)
    # original crop is 20x10 -> zoomed 3x -> 60x30
    assert crop.size == (60, 30)
