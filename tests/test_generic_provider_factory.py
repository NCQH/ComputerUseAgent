import pytest
from adaptivecua.config import build_provider
from adaptivecua.providers.vision.provider import GenericVisionProvider


def test_build_generic_with_injected_client():
    p = build_provider("generic", client=object(), display_size=(800, 600))
    assert isinstance(p, GenericVisionProvider)
    assert p.display_size == (800, 600)


def test_vision_alias():
    assert isinstance(build_provider("VISION", client=object()), GenericVisionProvider)


def test_unknown_still_raises():
    with pytest.raises(ValueError):
        build_provider("nope", client=object())
