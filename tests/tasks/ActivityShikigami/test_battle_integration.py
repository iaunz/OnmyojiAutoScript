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

    def __init__(self):
        self.conf = ActivityShikigami()
        self.conf.general_climb.run_sequence = 'pass,ap'
        self.run_idx = 0
        self.frames = 0
        self.result_visible = True
        self.win = True
        self.clicks = []
        self.device = SimpleNamespace(
            stuck_record_add=lambda name: None,
            click_record_clear=lambda: None,
        )

    def screenshot(self):
        self.frames += 1
        assert self.frames < 40, 'Activity battle did not settle'

    def is_in_battle(self, is_screenshot=True):
        return True

    def is_in_real_battle(self, is_screenshot=True):
        return False

    def appear(self, asset, **kwargs):
        result = self.I_UI_REWARD if self.win else self.I_FALSE
        return self.result_visible and asset is result

    def appear_then_click(self, asset, **kwargs):
        return False

    def click(self, asset, **kwargs):
        self.clicks.append(asset.name)
        self.result_visible = False

    def ui_click_until_disappear(self, asset, **kwargs):
        self.click(asset)

    def loadout_show(self, *args):
        pass

    def state_show(self):
        pass


@pytest.mark.parametrize('win', [True, False])
def test_activity_entry_uses_its_reward_strategy_and_counts_success_only(win):
    task = ActivityReplay()
    task.win = win
    # Decorating another task later must not replace Activity's selected hooks.
    battle_wait_strategy(success='default')(lambda owner, **kwargs: None)

    assert ScriptTask.battle_wait is Battle.battle_wait
    assert task.start_battle() is win
    assert task.count_map == {'pass': int(win), 'ap': 0}
    assert task.battle_count_reached(1)
    assert task.clicks == ['exclude_click_activity' if win else task.I_FALSE.name]
    assert battle_wait_strategy._context.get() is None


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
