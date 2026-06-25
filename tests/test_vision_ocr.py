from adaptivecua.providers.vision.ocr import detect_text_boxes


def _fake_ocr_factory(data):
    def _ocr(img):
        return data
    return _ocr


def test_extracts_boxes_above_confidence():
    data = {
        "text": ["Submit", "", "Cancel", "low"],
        "conf": ["95", "0", "88", "10"],
        "left": [10, 0, 100, 200],
        "top": [20, 0, 40, 60],
        "width": [50, 0, 40, 30],
        "height": [18, 0, 16, 12],
    }
    boxes = detect_text_boxes(None, ocr=_fake_ocr_factory(data), min_conf=40)
    # "Submit" (95) and "Cancel" (88) qualify; "" and conf=10 excluded
    assert boxes == [(10, 20, 60, 38), (100, 40, 140, 56)]


def test_malformed_rows_are_skipped():
    data = {
        "text": ["ok", "bad"],
        "conf": ["90", "not-a-number"],
        "left": [1, 2], "top": [1, 2], "width": [10, 10], "height": [10, 10],
    }
    boxes = detect_text_boxes(None, ocr=_fake_ocr_factory(data), min_conf=40)
    assert boxes == [(1, 1, 11, 11)]


def test_empty_when_no_qualifying_text():
    data = {"text": [""], "conf": ["0"], "left": [0], "top": [0], "width": [0], "height": [0]}
    assert detect_text_boxes(None, ocr=_fake_ocr_factory(data)) == []
