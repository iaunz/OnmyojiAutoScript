from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from module.exception import RequestHumanTakeover
from tasks.Restart.script_task import ScriptTask


@pytest.mark.parametrize('desktop,running', [(False, True), (True, True), (True, False)])
def test_restart_reuses_only_a_desktop_client_that_is_not_logged_in(desktop, running):
    calls = []
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(restart=SimpleNamespace(harvest_config=SimpleNamespace(enable_ap=False)))
    task.device = SimpleNamespace(
        is_desktop=desktop, app_is_running=lambda: running,
        app_stop=lambda: calls.append('stop'),
        desktop_stop_client=lambda: calls.append('stop') or True,
        app_start=lambda: calls.append('start'),
    )
    task._desktop_start_and_login = lambda: calls.append('desktop-login')
    task.app_handle_login = lambda: calls.append('login')
    task.set_next_run = lambda **kwargs: calls.append('scheduled')
    task.app_restart()
    assert calls == (['stop', 'start', 'login', 'scheduled'] if not desktop else
                     (['stop'] if running else []) + ['desktop-login', 'scheduled'])


def test_failed_desktop_stop_cannot_report_a_successful_restart():
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(restart=SimpleNamespace(harvest_config=SimpleNamespace(enable_ap=False)))
    task.device = SimpleNamespace(is_desktop=True, app_is_running=lambda: True,
                                  app_stop=lambda: None, desktop_stop_client=lambda: False)
    task._desktop_start_and_login = Mock()
    task.set_next_run = Mock()
    with pytest.raises(RequestHumanTakeover):
        task.app_restart()
    task._desktop_start_and_login.assert_not_called()
    task.set_next_run.assert_not_called()
