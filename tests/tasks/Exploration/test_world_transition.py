"""Replay post-battle transitions without a device or a 60-second watchdog wait."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tasks.Exploration.base import Scene
from tasks.Exploration.solo import SoloExploration


class SceneReplay(SoloExploration):
    def __init__(self, *frames):
        self.frames = iter(frames)
        self.frame = set()
        self.clicks = []
        self.device = SimpleNamespace(click_record_remove=Mock())
        self.interval_timer = {}

    def screenshot(self):
        frame = next(self.frames, None)
        assert frame is not None, 'Exploration kept waiting after the last replay frame'
        self.frame = set(frame)

    def appear(self, asset, **kwargs):
        return any(asset is getattr(self, name) for name in self.frame)

    def appear_then_click(self, asset, **kwargs):
        if self.appear(asset):
            self.clicks.append(asset)
            return True
        return False


@pytest.mark.parametrize('marker,scene', [
    ('I_E_EXPLORATION_CLICK', Scene.ENTRANCE),
    ('I_E_AUTO_ROTATE_ON', Scene.MAIN),
    ('I_E_AUTO_ROTATE_OFF', Scene.MAIN),
])
def test_chapter_controls_take_precedence_over_world_marker(marker, scene):
    task = SceneReplay(('I_CHECK_EXPLORATION', marker))
    assert task.get_current_scene(reuse_screenshot=False) == scene


@pytest.mark.parametrize('frame', [
    ('I_E_SETTINGS_BUTTON', 'I_EXP_ARROW_LEFT'), ('I_E_EXPLORATION_CLICK', 'I_EXP_ARROW_LEFT'),
    ('I_PREPARE_HIGHLIGHT', 'I_EXP_ARROW_LEFT'), ('I_BATTLE_INFO', 'I_EXP_ARROW_LEFT'),
    ('I_GI_EMOJI_1', 'I_EXP_ARROW_LEFT'), ('I_CHECK_EXPLORATION',), (),
])
def test_world_check_yields_unready_frames_without_clicking(frame):
    task = SceneReplay(frame)
    assert task.wait_world_stable() is False
    assert task.clicks == []


def test_hidden_world_panel_can_be_opened_when_its_marker_is_not_visible():
    task = SceneReplay(('I_EXP_ARROW_LEFT',), ('I_EXP_ARROW_LEFT',),
                       ('I_CHECK_EXPLORATION', 'I_EXP_ARROW_RIGHT'))
    assert task.get_current_scene(reuse_screenshot=False) == Scene.WORLD
    assert task.wait_world_stable() is False
    assert task.clicks == [task.I_EXP_ARROW_LEFT]
    assert task.wait_world_stable() is True
    assert task.clicks == [task.I_EXP_ARROW_LEFT]


@pytest.mark.parametrize('mode', ['run_solo', 'run_leader'])
def test_transient_world_after_battle_keeps_chapter_search_state(mode):
    task = SceneReplay(('I_CHECK_EXPLORATION',), ('I_E_SETTINGS_BUTTON',),
                       ('I_E_SETTINGS_BUTTON',),
                       ('I_CHECK_EXPLORATION',), ('I_CHECK_EXPLORATION', 'I_EXP_ARROW_RIGHT'))
    task.explore_init = True
    task.swipe_cnt = 2
    continued = []

    def handle_chapter():
        continued.append((task.explore_init, task.swipe_cnt))
        return True

    task._handle_treasure_box = handle_chapter
    task.check_exit = Mock(return_value=True)
    task.wait_until_stable = Mock()  # The leader also checks for a pending invite on exit.
    getattr(task, mode)()
    assert continued == [(True, 2)]
    task.device.click_record_remove.assert_called_once_with(task.S_SWIPE_BACKGROUND_RIGHT.name)
    task.check_exit.assert_called_once_with()
    assert not task.explore_init and task.swipe_cnt == 0
