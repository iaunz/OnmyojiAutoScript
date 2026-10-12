from types import SimpleNamespace

import pytest

from tasks.ActivityShikigami.config import ActivityShikigami
from tasks.ActivityShikigami.script_task import ScriptTask
from tasks.Component.GeneralBattle.battle import Battle
from tasks.Component.GeneralBattle.battle_wait import battle_wait_strategy, runtime


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(runtime, 'task_owner', None)
    monkeypatch.setattr(runtime, 'pub_ctx', None)
    monkeypatch.setattr(runtime, 'pri_ctx', {})
    monkeypatch.setattr('tasks.Component.GeneralBattle.battle_wait.random.random', lambda: 1)


class ActivityReplay(ScriptTask):
    """Exercise the real activity entry point and battle hooks without a device."""

    def __init__(self, *, reward_style='popup', return_delay=0):
        self.conf = ActivityShikigami()
        self.conf.general_climb.run_sequence = 'pass,ap'
        self.run_idx = 0
        self.frames = 0
        self.result_visible = True
        self.win = True
        self.reward_style = reward_style
        self.return_delay = return_delay
        self.return_frames = 0
        self.clicks = []
        self.device = SimpleNamespace(
            stuck_record_add=lambda name: None,
            click_record_clear=lambda: None,
        )

    def screenshot(self):
        self.frames += 1
        assert self.frames < 40, 'Activity battle did not settle'
        if not self.result_visible:
            self.return_frames += 1
            if self.return_frames <= self.return_delay:
                assert not self.battle_count_reached(1)

    def is_in_battle(self, is_screenshot=True):
        return True

    def is_in_real_battle(self, is_screenshot=True):
        return False

    def appear(self, asset, **kwargs):
        result = self.I_UI_REWARD if self.reward_style == 'popup' else self.I_REWARD
        if not self.win:
            result = self.I_FALSE
        if not self.result_visible and self.return_frames > self.return_delay:
            challenge = self.I_CHECK_BATTLE_BOSS if self.climb_type == 'boss' else self.I_CHECK_BATTLE_MAIN
            return asset.name == challenge.name
        return self.result_visible and asset is result

    def appear_then_click(self, asset, **kwargs):
        return False

    def click(self, asset, **kwargs):
        self.clicks.append(asset.name)
        self.result_visible = False
        return True

    def ui_click_until_disappear(self, asset, **kwargs):
        self.click(asset)

    def loadout_show(self, *args):
        pass

    def state_show(self):
        pass


@pytest.mark.parametrize('win', [True, False])
@pytest.mark.parametrize('reward_style', ['popup', 'standard'])
def test_activity_entry_handles_both_reward_styles_and_counts_success_only(win, reward_style):
    task = ActivityReplay(reward_style=reward_style)
    task.win = win
    # Decorating another task later must not replace Activity's selected hooks.
    battle_wait_strategy(success='default')(lambda owner, **kwargs: None)

    assert ScriptTask.battle_wait is Battle.battle_wait
    assert task.start_battle() is win
    assert task.count_map == {'pass': int(win), 'ap': 0}
    assert task.battle_count_reached(1)
    reward_click = 'exclude_click_activity' if reward_style == 'popup' else 'reward_exclude_click_2'
    assert task.clicks == [reward_click if win else task.I_FALSE.name]
    assert battle_wait_strategy._context.get() is None


@pytest.mark.parametrize('climb_type', ['pass', 'ap', 'boss'])
def test_completion_waits_for_the_current_challenge_screen(climb_type):
    task = ActivityReplay(return_delay=4)
    task.conf.general_climb.run_sequence = climb_type

    assert task.start_battle() is True
    assert task.return_frames > task.return_delay
    assert task.count_map == {climb_type: 1}
    assert task.clicks == ['exclude_click_activity']


def test_switching_climb_type_preserves_counts_and_resets_battle_state():
    task = ActivityReplay()
    assert task.start_battle() is True
    assert task.switch_next() is True
    assert task.count_map == {'pass': 1, 'ap': 0}
    assert not task.battle_count_reached(1)

    task.result_visible = True
    assert task.start_battle() is True
    assert task.count_map == {'pass': 1, 'ap': 1}
    assert task.switch_next() is False
