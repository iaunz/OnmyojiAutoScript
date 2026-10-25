from types import SimpleNamespace

import pytest

from tasks.AreaBoss.script_task import ScriptTask
from tasks.AreaBoss.config_boss import AreaBossFloor
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.battle_wait import battle_wait_strategy, battle_wait_options


@pytest.mark.parametrize('win', [True, False])
def test_start_fight_applies_configured_strategies_and_return_markers(win):
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(area_boss=SimpleNamespace(
        general_battle=GeneralBattleConfig(random_click_swipt_enable=True)))
    task.screenshot = lambda: None
    task.appear_then_click = lambda *args, **kwargs: False
    task.appear = lambda *args, **kwargs: False
    task.loadout_show = lambda *args: None
    strategies, options = task.loadout_from_config(task.config.area_boss.general_battle)
    seen = []
    def battle():
        plan = battle_wait_strategy._context.get()
        assert plan is not None
        assert all(getattr(plan, key) == value for key, value in strategies.items())
        active = battle_wait_options._context.get()
        assert active['completion'].check_imgs == [task.I_FIRE, task.I_FILTER]
        seen.append(True)
        return win
    task.battle_wait = battle
    assert task.start_fight() is win
    assert seen == [True]
    assert battle_wait_strategy._context.get() is None
    assert battle_wait_options._context.get() is None


@pytest.mark.parametrize('returned_to_filter', [True, False])
@pytest.mark.parametrize('win', [True, False])
def test_boss_fight_accepts_either_supported_return_screen(returned_to_filter, win):
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(area_boss=SimpleNamespace(boss=SimpleNamespace(reward_floor=AreaBossFloor.DEFAULT)))
    task.appear = lambda asset: asset is task.I_FILTER and returned_to_filter
    task.open_boss_detail = lambda *args: True
    task.is_group_ranked = lambda: False
    task.start_fight = lambda: win
    task.screenshot = lambda: None
    calls = []
    def wait(asset):
        assert not returned_to_filter, 'Already back at filter: red close will never appear'
        calls.append('wait')
    task.wait_until_appear = wait
    task.ui_click_until_disappear = lambda *args, **kwargs: calls.append('close')
    assert task.boss_fight(None, fileter_open=False) is win
    assert calls == ([] if returned_to_filter else ['wait', 'close'])
