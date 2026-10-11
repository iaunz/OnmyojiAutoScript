from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from module.exception import GameOcrError, TaskEnd
from tasks.RealmRaid.config import RealmRaid, WhenAttackFail
from tasks.RealmRaid.script_task import ScriptTask


def raid_replay(results, *, limit=30, exit_four=False, reward=False,
                failure_policy=WhenAttackFail.REFRESH):
    task = object.__new__(ScriptTask)
    config = RealmRaid()
    config.switch_soul_config.enable = False
    config.switch_soul_config.enable_switch_by_name = False
    config.raid_config.number_attack = limit
    config.raid_config.exit_four = exit_four
    config.raid_config.when_attack_fail = failure_policy
    task.config = SimpleNamespace(realm_raid=config)
    task.current_count = 0
    task.screenshot = Mock()
    task.goto_page = Mock()
    task.appear = Mock(return_value=False)
    task.ensure_lock = Mock()
    task.is_frog = Mock(return_value=False)
    task.check_ticket = Mock(return_value=True)
    task.find_one = Mock(return_value=(object(), 1 if exit_four else 2))
    task.check_medal_is_frog = Mock(return_value=False)
    task.fire = Mock()
    task.battle_before = Mock()
    task.is_in_battle = Mock(return_value=False)
    task.battle_wait = Mock(side_effect=results)
    task.run_general_battle_back = Mock(return_value=True)
    task.reward_detect_click = Mock(return_value=reward)
    task.is_realm_raid_page = Mock(return_value=True)
    task.check_refresh = Mock(return_value=True)
    task.ui_click = Mock()
    task.set_next_run = Mock()
    return task


@pytest.mark.parametrize('reward', [False, True])
def test_thirty_wins_allow_more_than_thirty_attempts(reward):
    task = raid_replay([True] * 12 + [False] + [True] * 18, reward=reward)
    with pytest.raises(TaskEnd):
        task.run_2()
    assert task.current_count == task.battle_wait.call_count == 31
    assert task.check_ticket.call_count == 32
    task.set_next_run.assert_called_once_with(task='RealmRaid', success=True, finish=True)


def test_retreat_four_does_not_consume_success_limit():
    task = raid_replay([True, False, True], limit=2, exit_four=True)
    with pytest.raises(TaskEnd):
        task.run_2()
    assert task.battle_wait.call_count == 3
    assert task.run_general_battle_back.call_count == 12


def test_no_tickets_can_still_end_before_success_limit():
    task = raid_replay([True])
    task.check_ticket.side_effect = [True, False]
    with pytest.raises(TaskEnd):
        task.run_2()
    assert task.battle_wait.call_count == 1
    task.set_next_run.assert_called_once_with(task='RealmRaid', success=True, finish=True)


def test_configured_exit_on_defeat_still_applies():
    task = raid_replay([False], failure_policy=WhenAttackFail.EXIT)
    with pytest.raises(TaskEnd):
        task.run_2()
    assert task.battle_wait.call_count == 1
    task.check_refresh.assert_not_called()


def test_transition_after_defeat_is_checked_before_refresh():
    task = raid_replay([False, True], limit=1)
    task.is_realm_raid_page.side_effect = [False, True]
    # 初次读票、战后页面恢复、下一轮读票、达到上限前确认页面。
    task.check_ticket.side_effect = [True, True, True, True]
    with pytest.raises(TaskEnd):
        task.run_2()
    assert task.battle_wait.call_count == 2
    task.check_refresh.assert_called_once_with()
    assert task.check_ticket.call_count == 4


def test_wrong_screen_after_battle_raises_recovery_before_refresh_or_exit():
    task = raid_replay([False])
    task.is_realm_raid_page.return_value = False
    task.check_ticket.side_effect = [True, GameOcrError('Wrong screen')]
    with pytest.raises(GameOcrError):
        task.run_2()
    task.check_refresh.assert_not_called()
    task.ui_click.assert_not_called()
    task.set_next_run.assert_not_called()
