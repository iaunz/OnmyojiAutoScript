from types import SimpleNamespace

import pytest

from module.base import timer
from tasks.Exploration.base import BaseExploration


class ExitReplay(BaseExploration):
    def __init__(self, monkeypatch, frames):
        self.frames = iter(frames)
        self.frame = set()
        self.clicks = []
        self.now = 100.0
        self.device = SimpleNamespace(click_record_remove=lambda name: None)
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))

    def screenshot(self):
        self.now += 0.5
        self.frame = next(self.frames)

    def appear(self, asset, **kwargs):
        return any(asset is getattr(self, name) for name in self.frame)

    def click(self, asset, **kwargs):
        self.clicks.append(asset)
        return True

    def appear_then_click(self, asset, **kwargs):
        return self.appear(asset) and self.click(asset, **kwargs)


@pytest.mark.parametrize('second_frame', [
    set(), {'I_BACK_YOLLOW'}, {'I_BACK_YOLLOW', 'I_E_EXPLORATION_CLICK'},
])
def test_exit_does_not_click_back_on_transition_or_unconfirmed_scene(monkeypatch, second_frame):
    task = ExitReplay(monkeypatch, [{'I_BACK_YOLLOW'}, second_frame, {'I_CHECK_EXPLORATION'}])
    task.quit_explore()
    assert task.clicks == []


@pytest.mark.parametrize('marker', ['I_E_SETTINGS_BUTTON', 'I_E_AUTO_ROTATE_ON', 'I_E_AUTO_ROTATE_OFF'])
def test_exit_clicks_back_only_on_verified_exploration_scene(monkeypatch, marker):
    task = ExitReplay(monkeypatch, [
        {'I_BACK_YOLLOW'}, {'I_BACK_YOLLOW', marker}, {'I_E_EXIT_CONFIRM'}, {'I_CHECK_EXPLORATION'},
    ])
    task.quit_explore()
    assert task.clicks == [task.I_BACK_YOLLOW, task.I_E_EXIT_CONFIRM]


@pytest.mark.parametrize('popup', ['I_E_EXIT_CONFIRM', 'I_BATTLE_REWARD'])
def test_exit_prioritizes_popup_appearing_on_second_screenshot(monkeypatch, popup):
    task = ExitReplay(monkeypatch, [
        {'I_BACK_YOLLOW'}, {'I_BACK_YOLLOW', 'I_E_SETTINGS_BUTTON', popup},
        {popup}, {'I_CHECK_EXPLORATION'},
    ])
    task.quit_explore()
    assert task.clicks == [getattr(task, popup)]
