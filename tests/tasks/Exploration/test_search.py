from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from module.base import timer
from module.base.timer import Timer
from tasks.Exploration.base import BaseExploration, Scene
from tasks.Exploration.config import UpType
from tasks.Exploration.solo import SoloExploration


def frame(value=0, scene=Scene.MAIN, popup=None):
    return value, scene, popup


class SearchReplay(SoloExploration):
    def __init__(self, monkeypatch, frames, up_type=UpType.ALL):
        self._config = SimpleNamespace(exploration_config=SimpleNamespace(up_type=up_type))
        self.now = 100.0
        self.frames = iter(frames)
        self.scene = Scene.MAIN
        self.popup = None
        self.swipes = []
        self.removed = []
        self.exits = 0
        self.swipe_cnt = 0
        self.device = SimpleNamespace(
            image=np.zeros((720, 1280, 3), dtype=np.uint8),
            click_record_remove=self.removed.append,
        )
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))
        monkeypatch.setattr('tasks.Exploration.solo.sleep', lambda _: None)
        self.search_fail_timer = Timer(self.SEARCH_SWIPE_INTERVAL)

    def screenshot(self):
        value, self.scene, self.popup = next(self.frames)
        self.device.image = np.full((720, 1280, 3), value, dtype=np.uint8)

    def swipe(self, asset):
        self.swipes.append(asset.name)

    def get_current_scene(self):
        return self.scene

    def appear(self, asset):
        return asset is self.popup

    def quit_explore(self):
        self.exits += 1

    def search(self):
        self._search_next_area()
        self.now += 2
        self._search_next_area()


def test_search_waits_for_no_target_interval(monkeypatch):
    task = SearchReplay(monkeypatch, [frame(80)])
    task._search_next_area()
    task.now += 1.4
    task._search_next_area()
    assert task.swipes == []
    task.now += 0.2
    task._search_next_area()
    assert len(task.swipes) == task.swipe_cnt == 1


@pytest.mark.parametrize('up_type', [UpType.EXP, UpType.COIN, UpType.DARUMAA])
def test_specific_up_restarts_after_two_search_swipes(monkeypatch, up_type):
    task = SearchReplay(monkeypatch, [], up_type)
    task.swipe_cnt = 2
    task.search()
    assert task.exits == 1
    assert task.swipe_cnt == 0
    assert not task.search_fail_timer.started()
    assert task.swipes == []


def test_all_targets_continues_past_two_swipes(monkeypatch):
    task = SearchReplay(monkeypatch, [frame(80)])
    task.swipe_cnt = 2
    task.search()
    assert task.exits == 0
    assert task.swipe_cnt == 3
    assert task.removed == [task.S_SWIPE_BACKGROUND_RIGHT.name]


def test_boundary_requires_a_second_swipe(monkeypatch):
    task = SearchReplay(monkeypatch, [frame(), frame(), frame()])
    task.search()
    assert len(task.swipes) == 2
    assert task.exits == 1


@pytest.mark.parametrize('frames,swipes', [([frame(), frame(80)], 1),
                                         ([frame(), frame(), frame(80)], 2)])
def test_delayed_or_initially_ignored_swipe_does_not_exit(monkeypatch, frames, swipes):
    task = SearchReplay(monkeypatch, frames)
    task.search()
    assert len(task.swipes) == swipes
    assert task.swipe_cnt == 1
    assert task.exits == 0


@pytest.mark.parametrize('retry', [False, True])
@pytest.mark.parametrize('interruption', ['battle', 'confirm', 'small-confirm'])
def test_swipe_interruption_returns_to_scene_handling(monkeypatch, retry, interruption):
    task = SearchReplay(monkeypatch, [])
    scene = Scene.BATTLE_PREPARE if interruption == 'battle' else Scene.MAIN
    popup = {'battle': None, 'confirm': task.I_UI_CONFIRM,
             'small-confirm': task.I_UI_CONFIRM_SAMLL}[interruption]
    frames = [frame(), frame(), frame(0, scene, popup)] if retry else [frame(80, scene, popup)]
    task.frames = iter(frames)
    task.search()
    assert task.exits == 0, 'A battle or popup must not be treated as the map boundary'
    assert task.swipe_cnt == 0
    assert len(task.swipes) == (2 if retry else 1)


def test_swipe_comparison_ignores_floating_effects_but_detects_background_motion():
    task = object.__new__(BaseExploration)
    before = np.zeros((720, 1280, 3), dtype=np.uint8)
    effects = before.copy()
    effects[86:311, 1216:1280] = 255
    assert task.is_swipe_unchanged(before, effects)
    background = before.copy()
    background[140:230, 250:1050] = 80
    assert not task.is_swipe_unchanged(before, background)


def test_specific_up_without_aligned_sword_does_not_attack_another_monster(monkeypatch):
    task = object.__new__(BaseExploration)
    task.device = SimpleNamespace(image=None)
    task.I_NORMAL_BATTLE_BUTTON = deepcopy(task.I_NORMAL_BATTLE_BUTTON)
    monkeypatch.setattr(task.I_NORMAL_BATTLE_BUTTON, 'match_all', lambda **kwargs: [])
    monkeypatch.setattr(task, 'appear', lambda asset: asset in (task.I_UP_EXP, task.I_NORMAL_BATTLE_BUTTON))
    assert task.search_up_fight(UpType.EXP) is None


def test_all_targets_restores_full_map_search(monkeypatch):
    task = object.__new__(BaseExploration)
    task.I_NORMAL_BATTLE_BUTTON = deepcopy(task.I_NORMAL_BATTLE_BUTTON)
    task.I_NORMAL_BATTLE_BUTTON.roi_back = (100, 100, 80, 80)

    def appear(asset):
        assert asset.roi_back == (0, 0, 1279, 719)
        return True

    monkeypatch.setattr(task, 'appear', appear)
    assert task.search_up_fight(UpType.ALL) is task.I_NORMAL_BATTLE_BUTTON
