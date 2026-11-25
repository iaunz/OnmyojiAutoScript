"""Replay battle return transitions without a running game or screenshot fixtures."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from module.base import timer
from module.exception import GameStuckError
from tasks.AreaBoss.config_boss import AreaBossFloor
from tasks.AreaBoss.script_task import ScriptTask


class AreaNavigationReplay(ScriptTask):
    def __init__(self, monkeypatch, *, screen='map', rebound=False,
                 ignored_closes=0, background_visible=False, win=True,
                 transitions=None, close_delay=0):
        # Keep the real navigation, recognition dispatch and click cooldowns.
        self.screen = screen
        self.rebound = rebound
        self.ignored_closes = ignored_closes
        self.background_visible = background_visible
        self.transitions = dict(transitions or {})
        self.close_delay = close_delay
        self.frames = 0
        self.now = 100.0
        self.interval_timer = {}
        self.clicks = []
        self.config = SimpleNamespace(area_boss=SimpleNamespace(
            boss=SimpleNamespace(reward_floor=AreaBossFloor.DEFAULT)))
        self.device = SimpleNamespace(image=frozenset(), click=self.record_click)
        self.start_fight = lambda: win
        for name in (
            'I_AB_CLOSE_RED', 'I_FIRE', 'I_FILTER', 'I_AB_FILTER_OPENED',
            'I_UI_BACK_YELLOW', 'I_CHECK_MAIN',
        ):
            asset = deepcopy(getattr(self, name))
            asset.match = lambda image, threshold=None, name=name: name in image
            setattr(self, name, asset)
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))

    def finish_first_battle(self):
        with patch.object(self, 'open_boss_detail', return_value=True):
            return self.boss_fight(self.I_BATTLE_1, fileter_open=False)

    def screenshot(self):
        self.frames += 1
        assert self.frames <= 200, 'Navigation did not finish or respect its timeout'
        self.now += 0.25
        if self.frames in self.transitions:
            self.screen = self.transitions.pop(self.frames)
        if self.rebound and self.frames == 3:
            self.screen = 'detail'
            self.rebound = False
        visible = {
            'map': {'I_FILTER', 'I_UI_BACK_YELLOW'},
            'detail': {'I_AB_CLOSE_RED', 'I_FIRE'},
            'detail_loading': {'I_AB_CLOSE_RED'},
            'detail_with_filter': {'I_AB_CLOSE_RED', 'I_AB_FILTER_OPENED'},
            'filter': {'I_AB_FILTER_OPENED'},
            'main': {'I_CHECK_MAIN'},
            'unknown': set(),
        }[self.screen].copy()
        if self.screen in ('detail', 'detail_loading') and self.background_visible:
            visible.update({'I_FILTER', 'I_UI_BACK_YELLOW'})
        self.device.image = frozenset(visible)

    def record_click(self, x, y, control_name):
        self.clicks.append((control_name, self.now))
        if control_name == self.I_AB_CLOSE_RED.name:
            assert self.screen in ('detail', 'detail_with_filter')
            if self.ignored_closes:
                self.ignored_closes -= 1
            elif self.screen == 'detail_with_filter':
                # The first tap outside the list can dismiss just the list.
                self.screen = 'detail'
            elif self.close_delay:
                self.screen = 'unknown'
                self.transitions[self.frames + self.close_delay] = 'map'
            else:
                self.screen = 'map'
        elif control_name == self.I_FILTER.name:
            assert self.screen == 'map', 'Clicked filter behind the boss detail'
            if not self.rebound:
                self.screen = 'filter'
        elif control_name == self.I_UI_BACK_YELLOW.name:
            assert self.screen == 'map', 'Clicked back behind the boss detail'
            if not self.rebound:
                self.screen = 'main'
        elif control_name == self.I_BATTLE_2.name:
            assert self.screen == 'filter', 'Selected a boss while the previous detail was open'
            # The list can still be folding away as the selected detail appears.
            self.screen = 'detail_with_filter'
            self.transitions[self.frames + 3] = 'detail'
        else:
            pytest.fail(f'Unexpected click: {control_name}')

    @property
    def clicked_names(self):
        return [name for name, _ in self.clicks]


@pytest.mark.parametrize('navigate, destination, navigation_asset', [
    ('open_filter', 'filter', 'I_FILTER'),
    ('go_back', 'main', 'I_UI_BACK_YELLOW'),
])
@pytest.mark.parametrize('win', [True, False])
def test_battle_return_recovers_detail_reappearing_after_map(
        monkeypatch, navigate, destination, navigation_asset, win):
    task = AreaNavigationReplay(monkeypatch, rebound=True, win=win,
                                ignored_closes=3, background_visible=True)

    assert task.finish_first_battle() is win
    assert task.clicked_names == [task.I_AB_CLOSE_RED.name] * 4
    getattr(task, navigate)()

    assert task.screen == destination
    button = getattr(task, navigation_asset).name
    assert task.clicked_names == [task.I_AB_CLOSE_RED.name] * 4 + [button]
    close_times = [at for name, at in task.clicks if name == task.I_AB_CLOSE_RED.name]
    assert all(later - earlier >= 1 for earlier, later in zip(close_times, close_times[1:]))


def test_battle_return_closes_detail_under_filter_before_selecting_second_boss(monkeypatch):
    task = AreaNavigationReplay(monkeypatch, screen='map', transitions={3: 'detail_with_filter'})
    close = task.I_AB_CLOSE_RED.name

    assert task.finish_first_battle()
    assert task.screen == 'map'
    assert task.clicked_names == [close, close]

    assert task.boss_fight(task.I_BATTLE_2)
    assert task.clicked_names == [close, close, task.I_FILTER.name, task.I_BATTLE_2.name, close]


def test_second_boss_selection_recovers_filter_already_over_detail(monkeypatch):
    task = AreaNavigationReplay(monkeypatch, screen='detail_with_filter')
    task.screenshot()

    assert task.boss_fight(task.I_BATTLE_2)

    close = task.I_AB_CLOSE_RED.name
    assert task.clicked_names == [close, close, task.I_FILTER.name, task.I_BATTLE_2.name, close]


def test_reward_boss_fights_already_selected_detail(monkeypatch):
    task = AreaNavigationReplay(monkeypatch, screen='detail')

    assert task.boss_fight(task.C_AB_BOSS_REWARD_PHOTO_1, fileter_open=False)
    assert task.clicked_names == [task.I_AB_CLOSE_RED.name]


def test_unavailable_boss_retries_only_on_clear_list(monkeypatch):
    task = AreaNavigationReplay(monkeypatch, screen='filter')
    def ignore_selection(x, y, control_name):
        assert task.screen == 'filter'
        task.clicks.append((control_name, task.now))
    task.device.click = ignore_selection

    assert not task.boss_fight(task.I_BATTLE_2)
    assert task.clicked_names == [task.I_BATTLE_2.name] * 3
    assert all(later - earlier >= 3 for (_, earlier), (_, later) in zip(task.clicks, task.clicks[1:]))


@pytest.mark.parametrize('navigate, destination', [
    ('open_filter', 'filter'), ('go_back', 'main'),
])
@pytest.mark.parametrize('screen', ['map', 'detail'])
def test_battle_return_still_accepts_direct_map_and_normal_detail(
        monkeypatch, navigate, destination, screen):
    task = AreaNavigationReplay(monkeypatch, screen=screen)

    assert task.finish_first_battle() is True
    getattr(task, navigate)()

    assert task.screen == destination
    assert task.clicked_names.count(task.I_AB_CLOSE_RED.name) == (screen == 'detail')


@pytest.mark.parametrize('navigate, screen', [
    ('open_filter', 'filter'), ('go_back', 'main'),
])
def test_arrived_navigation_target_needs_no_click(monkeypatch, navigate, screen):
    task = AreaNavigationReplay(monkeypatch, screen=screen)

    getattr(task, navigate)()

    assert task.screen == screen
    assert task.clicks == []


@pytest.mark.parametrize('navigate', ['open_filter', 'go_back'])
@pytest.mark.parametrize('screen', ['unknown', 'detail'])
def test_navigation_times_out_when_page_never_changes(monkeypatch, navigate, screen):
    task = AreaNavigationReplay(monkeypatch, screen=screen, ignored_closes=100)

    with pytest.raises(GameStuckError):
        getattr(task, navigate)()

    assert task.now <= 125
    assert task.screen == screen
    assert all(name == task.I_AB_CLOSE_RED.name for name in task.clicked_names)


@pytest.mark.parametrize('screen', ['map', 'filter'])
@pytest.mark.parametrize('win', [True, False])
def test_battle_return_waits_through_unknown_frames(monkeypatch, screen, win):
    task = AreaNavigationReplay(monkeypatch, screen='unknown', win=win,
                                transitions={3: screen})

    assert task.finish_first_battle() is win

    assert task.screen == screen
    assert task.clicks == []


def test_battle_return_waits_for_map_after_detail_close_animation(monkeypatch):
    task = AreaNavigationReplay(monkeypatch, screen='detail', close_delay=3)

    assert task.finish_first_battle() is True

    assert task.screen == 'map'
    assert task.clicked_names == [task.I_AB_CLOSE_RED.name]


@pytest.mark.parametrize('screen', ['unknown', 'detail'])
def test_battle_return_times_out_without_a_confirmed_page(monkeypatch, screen):
    task = AreaNavigationReplay(monkeypatch, screen=screen, ignored_closes=100)

    with pytest.raises(GameStuckError):
        task.finish_first_battle()

    assert task.now <= 125
    assert task.screen == screen
    assert all(name == task.I_AB_CLOSE_RED.name for name in task.clicked_names)


@pytest.mark.parametrize('navigate, destination', [
    ('boss_fight', 'map'), ('open_filter', 'filter'), ('go_back', 'main'),
])
def test_detail_loading_blocks_background_controls_until_ready(
        monkeypatch, navigate, destination):
    task = AreaNavigationReplay(monkeypatch, screen='detail_loading',
                                transitions={5: 'detail'}, background_visible=True)

    if navigate == 'boss_fight':
        assert task.finish_first_battle() is True
    else:
        getattr(task, navigate)()

    assert task.screen == destination
    assert task.clicked_names[0] == task.I_AB_CLOSE_RED.name
    assert task.clicks[0][1] >= 101.25
