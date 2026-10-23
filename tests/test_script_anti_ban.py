from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import script as script_module
from module.config import anti_ban as anti_ban_module
from tasks.Script.config_antiban import AntiBan
from tasks.Script.config_optimization import Optimization, WhenTaskQueueEmpty


@pytest.fixture
def scheduler(monkeypatch):
    clock = SimpleNamespace(now=datetime(2026, 10, 23, 3))

    class Clock(datetime):
        @classmethod
        def now(cls):
            return clock.now

    monkeypatch.setattr(script_module, 'datetime', Clock)
    monkeypatch.setattr(anti_ban_module, 'datetime', Clock)
    task = SimpleNamespace(command='Exploration', next_run=clock.now - timedelta(minutes=1))
    script = object.__new__(script_module.Script)
    script._emulator_down = False
    script.instance_guard = None
    script.state_queue = None
    script.anti_ban_guard = anti_ban_module.AntiBanGuard()
    script.config = SimpleNamespace(
        script=SimpleNamespace(
            anti_ban=AntiBan(enable=True),
            optimization=Optimization(
                close_game_wait_duration=time(12),
                close_emulator_wait_duration=time(0, 1),
            ),
        ),
        get_next=Mock(return_value=task),
    )
    script._try_acquire_queue_token = Mock(return_value=True)
    script.device = Mock()
    script.run = Mock(return_value=True)
    script._wait_until_with_emulator_preheat = Mock(return_value=True)

    def finish_wait(future):
        clock.now = future + timedelta(seconds=1)
        return True

    script.wait_until = Mock(side_effect=finish_wait)
    events = Mock()
    events.attach_mock(script.device.app_stop, 'close_game')
    events.attach_mock(script.device.emulator_stop, 'close_emulator')
    events.attach_mock(script.device.release_during_wait, 'release')
    events.attach_mock(script.run, 'run')
    events.attach_mock(script.wait_until, 'wait')
    return script, clock, task, events


@pytest.mark.parametrize('method', list(WhenTaskQueueEmpty))
@pytest.mark.parametrize('trigger', ['sleep_window', 'active_limit'])
def test_anti_ban_finishes_using_selected_action_before_waiting(scheduler, method, trigger):
    script, clock, task, events = scheduler
    script.config.script.optimization.when_task_queue_empty = method
    original_next_run = task.next_run
    if trigger == 'active_limit':
        config = script.config.script.anti_ban
        config.sleep_start = config.sleep_end = time(0)
        config.daily_active_limit = timedelta(hours=1)
        config.long_rest_duration = timedelta(minutes=5)
        script.anti_ban_guard.record_active(3600)
        wake = clock.now + config.long_rest_duration
    else:
        wake = clock.now.replace(hour=8)

    assert script.get_next_task() == 'Exploration'

    # Both ordinary idle thresholds would change the requested action:
    # the game-close threshold is longer than the rest, the emulator threshold shorter.
    if method == WhenTaskQueueEmpty.CLOSE_GAME:
        assert events.mock_calls == [
            call.close_game(), call.release(), call.wait(wake), call.run('Restart'),
        ]
    else:
        assert events.mock_calls == [
            call.run('GotoMain'), call.release(), call.wait(wake),
        ]
    assert script.config.get_next.call_count == 2
    assert task.next_run == original_next_run
    script._wait_until_with_emulator_preheat.assert_not_called()


@pytest.mark.parametrize('method', list(WhenTaskQueueEmpty))
@pytest.mark.parametrize('trigger', ['sleep_window', 'active_limit'])
def test_anti_ban_waits_for_running_task_to_finish(scheduler, monkeypatch, method, trigger):
    script, clock, task, events = scheduler
    clock.now = datetime(2026, 10, 23, 1, 59, 30)
    task.next_run = clock.now - timedelta(minutes=1)
    script.config_name = 'anti_ban_test'
    script.is_first_task = False
    script.failure_record = {}
    script.config.model = SimpleNamespace(running_task='')
    script.config.script.device = SimpleNamespace(run_background_only=True)
    script.config.script.optimization.when_task_queue_empty = method
    script.device.is_desktop = False
    if trigger == 'active_limit':
        config = script.config.script.anti_ban
        config.sleep_start = config.sleep_end = time(0)
        config.daily_active_limit = timedelta(minutes=1)
        config.long_rest_duration = timedelta(minutes=5)
    check_anti_ban = Mock(wraps=script.anti_ban_guard.wake_time)
    monkeypatch.setattr(script.anti_ban_guard, 'wake_time', check_anti_ban)
    monkeypatch.setattr(script_module.logger, 'set_file_logger', Mock())
    monkeypatch.setattr(script_module, 'del_cached_property', Mock())
    task_finished = False

    def run(command):
        nonlocal task_finished
        if command == 'Exploration':
            assert script.config.model.running_task == 'Exploration'
            # Cross the sleep start / active limit while the same task is still running.
            clock.now += timedelta(minutes=1)
            assert check_anti_ban.call_count == 1
            assert events.mock_calls == [call.run('Exploration')]
            clock.now += timedelta(minutes=1)
            task_finished = True
            events.task_complete()
        else:
            assert command == 'GotoMain'
            assert task_finished
        return True

    class RestStarted(Exception):
        pass

    def wait(future):
        assert task_finished
        assert script.config.model.running_task == ''
        assert check_anti_ban.call_count == 2
        raise RestStarted

    script.run.side_effect = run
    script.wait_until.side_effect = wait

    with pytest.raises(RestStarted):
        script.loop()

    wake = (clock.now + timedelta(minutes=5) if trigger == 'active_limit'
            else clock.now.replace(hour=8, minute=0, second=0))
    cleanup = call.close_game() if method == WhenTaskQueueEmpty.CLOSE_GAME else call.run('GotoMain')
    assert events.mock_calls == [
        call.run('Exploration'), call.task_complete(), cleanup, call.release(), call.wait(wake),
    ]


@pytest.mark.parametrize('method', list(WhenTaskQueueEmpty))
def test_disabling_anti_ban_during_wait_reloads_without_delaying_pending_task(
        scheduler, monkeypatch, method):
    script, clock, task, events = scheduler
    script.config.script.optimization.when_task_queue_empty = method
    original_next_run = task.next_run
    script.wait_until.side_effect = None
    script.wait_until.return_value = False

    def reload_config(instance, name):
        assert instance is script
        assert name == 'config'
        script.config.script.anti_ban.enable = False

    reload = Mock(side_effect=reload_config)
    monkeypatch.setattr(script_module, 'del_cached_property', reload)

    assert script.get_next_task() == 'Exploration'

    reload.assert_called_once_with(script, 'config')
    script.wait_until.assert_called_once_with(clock.now.replace(hour=8))
    assert task.next_run == original_next_run
    assert call.run('Restart') not in events.mock_calls


@pytest.mark.parametrize('method', list(WhenTaskQueueEmpty))
def test_anti_ban_keeps_stopped_emulator_off_without_preheating(scheduler, method):
    script, clock, task, events = scheduler
    script.config.script.optimization.when_task_queue_empty = method
    script._emulator_down = True

    assert script.get_next_task() == 'Exploration'

    assert events.mock_calls == [call.wait(datetime(2026, 10, 23, 8))]
    script._wait_until_with_emulator_preheat.assert_not_called()
    assert script._emulator_down is True


def test_ordinary_short_idle_keeps_game_open_below_close_threshold(scheduler):
    script, clock, task, events = scheduler
    script.config.script.optimization.when_task_queue_empty = WhenTaskQueueEmpty.CLOSE_GAME
    next_run = clock.now + timedelta(seconds=30)

    assert script._handle_wait_during_idle(next_run) is True

    assert events.mock_calls == [call.release(), call.wait(next_run)]


@pytest.mark.parametrize('method', list(WhenTaskQueueEmpty))
def test_ordinary_long_idle_still_closes_emulator_at_configured_threshold(scheduler, method):
    script, clock, task, events = scheduler
    script.config.script.optimization.when_task_queue_empty = method
    next_run = clock.now + timedelta(minutes=5)

    assert script._handle_wait_during_idle(next_run) is True

    assert events.mock_calls == [call.close_emulator(), call.run('Restart')]
    script._wait_until_with_emulator_preheat.assert_called_once_with(next_run)
