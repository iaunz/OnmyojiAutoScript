"""Replay the reported in-scene chest, which is distinct from the reward title."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from tasks.Exploration.assets import ExplorationAssets
from tasks.Exploration.base import Scene
from tasks.Exploration.solo import SoloExploration


@pytest.fixture
def chest_crop():
    # User screenshot from 2026-10-10, resized from 1404x790 to 1280x720,
    # then cropped to (500, 340, 260, 200). Keep this independent of the template.
    path = Path(__file__).with_name('fixtures') / 'scene_chest.png'
    return cv2.cvtColor(cv2.imdecode(np.fromfile(path, dtype=np.uint8),
                                   cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def scene_with_chest(crop, x=500, y=340):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    height, width = crop.shape[:2]
    image[y:y + height, x:x + width] = crop
    return image


def reward_popup():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    title = ExplorationAssets.I_GET_REWARD.image
    height, width = title.shape[:2]
    image[206:206 + height, 514:514 + width] = title
    return image


@pytest.mark.parametrize('position', [(100, 180), (500, 340), (900, 400)])
def test_scene_chest_is_found_at_different_map_positions(chest_crop, position):
    rule = deepcopy(ExplorationAssets.I_BATTLE_REWARD)
    x, y = position

    assert rule.match(scene_with_chest(chest_crop, x, y))
    # The clasp is at (81, 69) within the crop; a click must land inside it.
    click_x, click_y = rule.coord()
    assert x + 81 <= click_x < x + 112
    assert y + 69 <= click_y < y + 90


def test_reward_popup_is_not_an_unopened_chest():
    image = reward_popup()

    assert deepcopy(ExplorationAssets.I_GET_REWARD).match(image)
    assert not deepcopy(ExplorationAssets.I_BATTLE_REWARD).match(image)


class RewardCollected(Exception):
    """Stop the exploration loop once the replay has collected its reward."""


class ExplorationRewardReplay(SoloExploration):
    def __init__(self, chest_crop):
        self.explore_init = True
        self.interval_timer = {}
        self.screen = 'chest'
        self.frames = 0
        self.clicks = []
        self.images = {
            'chest': scene_with_chest(chest_crop),
            'reward': reward_popup(),
            'done': np.zeros((720, 1280, 3), dtype=np.uint8),
        }
        self.device = SimpleNamespace(image=self.images[self.screen], click=self.record_click)
        self.I_BATTLE_REWARD = deepcopy(self.I_BATTLE_REWARD)
        self.I_UI_REWARD = deepcopy(self.I_UI_REWARD)

    def screenshot(self):
        self.frames += 1
        assert self.frames < 15, 'Reward collection did not finish'
        self.device.image = self.images[self.screen]

    def get_current_scene(self, reuse_screenshot=True):
        if self.screen == 'done':
            raise RewardCollected
        return Scene.MAIN

    def record_click(self, x, y, control_name):
        self.clicks.append(control_name)
        if self.screen == 'chest':
            assert control_name == self.I_BATTLE_REWARD.name
            assert 581 <= x < 612 and 409 <= y < 430
            self.screen = 'reward'
        else:
            assert self.screen == 'reward'
            assert control_name == self.I_UI_REWARD.name
            self.screen = 'done'

    def search_up_fight(self):
        pytest.fail('Started searching for enemies while a chest was visible')

    def _check_mate_leave(self, friend_leave_timer):
        pytest.fail('Checked for a missing teammate before collecting the chest')


@pytest.mark.parametrize('mode', ['run_solo', 'run_leader', 'run_member'])
def test_all_exploration_modes_open_the_chest_and_collect_rewards(chest_crop, monkeypatch, mode):
    monkeypatch.setattr('tasks.base_task.sleep', lambda _: None)
    task = ExplorationRewardReplay(chest_crop)

    with pytest.raises(RewardCollected):
        getattr(task, mode)()

    assert task.clicks == [task.I_BATTLE_REWARD.name, task.I_UI_REWARD.name]
