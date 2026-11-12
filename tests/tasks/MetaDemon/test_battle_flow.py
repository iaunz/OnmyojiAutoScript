import pytest

from module.exception import GameStuckError
from tasks.Component.GeneralBattle.battle_wait import runtime
from tasks.MetaDemon import script_task


@pytest.mark.parametrize('win', [True, False])
def test_boss_battle_unlocks_and_finishes_on_result_screen(monkeypatch, win):
    monkeypatch.setattr(runtime, 'pub_ctx', None)
    monkeypatch.setattr(runtime, 'pri_ctx', {})
    monkeypatch.setattr(runtime, 'task_owner', None)
    monkeypatch.setattr(script_task, 'sleep', lambda _: None)
    task = script_task.ScriptTask.__new__(script_task.ScriptTask)
    result = task.I_MD_WIN if win else task.I_MD_BATTLE_FAILURE
    visible = {task.I_TEAM_LOCK.name, task.I_BATTLE_DEMON.name}
    clicks = []
    frames = iter(range(18))
    task.screenshot = lambda: next(frames)
    task.appear = lambda rule, **kwargs: rule.name in visible
    task.refresh_long_time = lambda: None
    task.is_in_real_battle = lambda *args: False

    def click(rule, **kwargs):
        clicks.append(rule.name)
        visible.remove(rule.name)
        if rule is task.I_TEAM_LOCK:
            visible.add(task.I_TEAM_UNLOCK.name)
        elif rule is task.I_BATTLE_DEMON:
            visible.add(result.name)
        else:
            assert rule is result
            visible.add(task.I_FIND_DEMON.name)
        return True

    task.click = click
    task.appear_then_click = lambda rule, **kwargs: task.appear(rule) and task.click(rule)
    assert task.battle_boss() is win
    assert clicks == [task.I_TEAM_LOCK.name, task.I_BATTLE_DEMON.name, result.name]
    assert runtime.pub_ctx.per_task.count == 1


def test_missing_unlock_confirmation_stops_before_challenging():
    task = object.__new__(script_task.ScriptTask)
    task.ui_click = lambda *args, **kwargs: False
    with pytest.raises(GameStuckError, match='unlock'):
        task.battle_boss()
