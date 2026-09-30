from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from module.atom.image import RuleImage
from tasks.Component.Costume import costume_base
from tasks.Component.Costume.assets import CostumeAssets
from tasks.Component.Costume.config import MainType


def screenshot_for(asset):
    image = asset.image
    x, y = asset.roi_front[:2]
    height, width = image.shape[:2]
    screenshot = np.zeros((720, 1280, 3), dtype=np.uint8)
    screenshot[y:y + height, x:x + width] = image
    return screenshot


@pytest.mark.parametrize('animated_type', [MainType.COSTUME_MAIN_13, MainType.COSTUME_MAIN_17])
def test_switch_animated_to_static_and_back_preserves_shared_reference(monkeypatch, animated_type):
    # Match real costume templates without mutating the process-wide asset objects.
    assets = SimpleNamespace(**{
        name: deepcopy(value)
        for name, value in vars(CostumeAssets).items()
        if isinstance(value, RuleImage)
    })
    monkeypatch.setattr(costume_base, 'CostumeAssets', lambda: assets)
    host = costume_base.CostumeBase()
    host.I_CHECK_MAIN = deepcopy(assets.I_CHECK_MAIN_2)
    page_reference = host.I_CHECK_MAIN

    # Prime the static image cache before changing to a GIF costume.
    assert page_reference.match(screenshot_for(assets.I_CHECK_MAIN_2))
    host.check_costume_main(animated_type)
    frame_names = costume_base.main_costume_model[animated_type]['I_CHECK_MAIN']
    animated_screen = screenshot_for(getattr(assets, frame_names[-1]))
    assert page_reference.match(animated_screen)

    host.check_costume_main(MainType.COSTUME_MAIN_1)
    assert host.I_CHECK_MAIN is page_reference
    assert page_reference.match(screenshot_for(assets.I_CHECK_MAIN_1))
    assert not page_reference.match(animated_screen)
    assert not hasattr(page_reference, 'targets')
    assert page_reference.name == assets.I_CHECK_MAIN_1.name

    # A second static costume must not reuse the first static template's cache.
    host.check_costume_main(MainType.COSTUME_MAIN_2)
    assert page_reference.match(screenshot_for(assets.I_CHECK_MAIN_2))

    host.check_costume_main(animated_type)
    assert host.I_CHECK_MAIN is page_reference
    assert page_reference.match(animated_screen)
    assert page_reference.name == getattr(assets, frame_names[0]).name
