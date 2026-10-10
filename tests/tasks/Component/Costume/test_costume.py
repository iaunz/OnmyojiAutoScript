from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import cv2

from module.atom.image import RuleImage
from tasks.Component.Costume import costume_base
from tasks.Component.Costume.assets import CostumeAssets
from tasks.Component.Costume.config import MainType, BattleSceneType
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets


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


def make_rule(tmp_path, name, size, method, masked=False):
    pixels = np.random.default_rng(size).integers(0, 256, (size, size, 3), dtype=np.uint8)
    path = tmp_path / f'{name}.png'
    path.write_bytes(cv2.imencode('.png', pixels)[1].tobytes())
    if masked:
        mask = np.zeros((size, size), dtype=np.uint8)
        mask[:, :size // 2] = 255
        path.with_name(f'{name}_mask.png').write_bytes(cv2.imencode('.png', mask)[1].tobytes())
    return RuleImage((10, 10, size, size), (0, 0, 80, 80), method, 0.99, str(path))


def masked_screenshot(asset):
    screen = np.zeros((80, 80, 3), dtype=np.uint8)
    image = asset.image.copy()
    image[:, image.shape[1] // 2:] = 0
    screen[10:10 + image.shape[0], 10:10 + image.shape[1]] = image
    return screen


def test_replace_img_invalidates_plain_to_masked_dispatch(tmp_path):
    host = costume_base.CostumeBase()
    host.I_CHECK_MAIN = make_rule(tmp_path, 'plain', 20, 'Template matching')
    masked = make_rule(tmp_path, 'masked', 20, 'Masked template matching', masked=True)
    screen = masked_screenshot(masked)
    assert not host.I_CHECK_MAIN.match(screen)

    host.replace_img('I_CHECK_MAIN', masked)

    assert host.I_CHECK_MAIN.match(screen)


def test_replace_img_loads_the_new_mask_after_size_changes(tmp_path):
    host = costume_base.CostumeBase()
    host.I_CHECK_MAIN = make_rule(tmp_path, 'old', 20, 'Masked template matching', masked=True)
    assert host.I_CHECK_MAIN.match(masked_screenshot(host.I_CHECK_MAIN))
    replacement = make_rule(tmp_path, 'new', 24, 'Masked template matching', masked=True)

    host.replace_img('I_CHECK_MAIN', replacement)

    assert host.I_CHECK_MAIN.match(masked_screenshot(replacement))
    assert host.I_CHECK_MAIN.mask.shape == (24, 24)


def test_replace_img_invalidates_multi_scale_dispatch(tmp_path):
    host = costume_base.CostumeBase()
    host.I_CHECK_MAIN = make_rule(tmp_path, 'scaled', 20, 'Multi-scale template matching')
    screen = np.zeros((80, 80, 3), dtype=np.uint8)
    screen[10:26, 10:26] = cv2.resize(host.I_CHECK_MAIN.image, (16, 16))
    assert host.I_CHECK_MAIN.match(screen)
    replacement = make_rule(tmp_path, 'plain', 20, 'Template matching')

    host.replace_img('I_CHECK_MAIN', replacement)

    assert not host.I_CHECK_MAIN.match(screen)


def test_battle_scene_override_is_isolated_to_the_allowed_task():
    class Task(costume_base.CostumeBase):
        I_REWARD = deepcopy(GeneralBattleAssets.I_REWARD)

        def __init__(self, name):
            self.name = name

        def get_task_name(self):
            return self.name

    original = Task.I_REWARD
    original_file = original.file
    orochi = Task('Orochi')
    orochi.check_costume_battle_scene(BattleSceneType.COSTUME_BATTLE_SCENE_1)
    assert orochi.I_REWARD is not original
    assert orochi.I_REWARD.file != original_file
    assert orochi.I_REWARD.match(screenshot_for(orochi.I_REWARD))

    next_task = Task('RealmRaid')
    next_task.check_costume_battle_scene(BattleSceneType.COSTUME_BATTLE_SCENE_1)
    assert next_task.I_REWARD is original
    assert next_task.I_REWARD.file == original_file
    assert next_task.I_REWARD.match(screenshot_for(original))

    orochi.check_costume_battle_scene(BattleSceneType.COSTUME_BATTLE_SCENE_DEFAULT)
    assert orochi.I_REWARD is original
