import numpy as np
import pytest

from module.atom import image as image_module
from module.atom.image import RuleImage


@pytest.mark.parametrize('method', ['match', 'match_multi_scale', 'match_all', 'match_all_any'])
@pytest.mark.parametrize('position', [(0, 0), (16, 17)])
@pytest.mark.parametrize('pad', [0, 2])
def test_matching_padding_preserves_absolute_coordinates(monkeypatch, method, position, pad):
    monkeypatch.setattr(image_module, 'ROI_MATCH_PAD', pad)
    template = np.random.default_rng(19).integers(0, 256, (10, 10, 3), dtype=np.uint8)
    screen = np.zeros((40, 40, 3), dtype=np.uint8)
    x, y = position
    screen[y:y + 10, x:x + 10] = template
    # Desktop padding compensates for a one-pixel displacement; emulator uses exact ROI.
    roi = (x + bool(pad), y + bool(pad), 10, 10)
    rule = RuleImage(roi, roi, 'Template matching', 0.99, 'unused.png')
    rule._image = template
    if method == 'match_multi_scale':
        assert rule.match_multi_scale(screen, scales=[1.0])
        assert tuple(rule.roi_front[:2]) == position
    elif method == 'match':
        assert rule.match(screen)
        assert tuple(rule.roi_front[:2]) == position
    else:
        results = getattr(rule, method)(screen)
        assert any(tuple(result[1:3]) == position for result in results)


def test_emulator_without_padding_does_not_accept_shifted_template(monkeypatch):
    monkeypatch.setattr(image_module, 'ROI_MATCH_PAD', 0)
    pixels = np.random.default_rng(19).integers(0, 256, (10, 10, 3), dtype=np.uint8)
    screen = np.zeros((30, 30, 3), dtype=np.uint8)
    screen[10:20, 10:20] = pixels
    rule = RuleImage((11, 11, 10, 10), (11, 11, 10, 10), 'Template matching', 0.99, 'unused.png')
    rule._image = pixels
    assert not rule.match(screen)
