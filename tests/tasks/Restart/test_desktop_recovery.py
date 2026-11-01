from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import script as script_module
from module.device.method import desktop_impl as desktop
from module.device.desktop_device import DesktopDevice
from module.exception import GameNotRunningError, RequestHumanTakeover, TaskEnd
from tasks.Restart.script_task import ScriptTask


@pytest.mark.parametrize('just_launched,popup,expected', [
    (True, 0, False), (False, 0, True), (False, 99, False),
])
def test_binding_distinguishes_new_client_from_existing_login(monkeypatch, just_launched, popup, expected):
    window = desktop.DesktopWindow()
    window.desktop_profile_dir = lambda: None
    window.find_desktop_login_popup = Mock(return_value=popup)
    monkeypatch.setattr(desktop, 'desktop_keep_screen_on', Mock())
    monkeypatch.setattr(desktop, 'desktop_write_instance_state', Mock())
    window.desktop_bind_pid(123, just_launched=just_launched)
    assert window._desktop_login_done is expected
    assert window._desktop_just_launched is just_launched
    assert window.find_desktop_login_popup.call_count == (0 if just_launched else 1)


@pytest.mark.parametrize('logged_in', [False, True])
def test_force_restart_reuses_owned_window_only_until_first_login(logged_in):
    class Client(desktop.DesktopWindow, DesktopDevice):
        pass

    client = Client()
    client.root_handle = '123'
    client._desktop_spawned_pids = {123}
    client._desktop_just_launched = True
    client._desktop_login_done = False
    client.desktop_window_exists = lambda: True
    client.desktop_stop_client = Mock(return_value=True)
    if logged_in:
        client.desktop_mark_logged_in()
        # Later loss of login must not restore the fresh-launch exemption.
        client.desktop_mark_logged_out()
    task = object.__new__(ScriptTask)
    task.device = client
    task._desktop_start_and_login = Mock()
    task._desktop_restart_and_login()
    assert client.desktop_stop_client.call_count == int(logged_in)
    task._desktop_start_and_login.assert_called_once_with()


@pytest.mark.parametrize('exists,stop_ok', [(False, True), (True, True), (True, False)])
def test_force_restart_existing_or_absent_window(exists, stop_ok):
    task = object.__new__(ScriptTask)
    task.device = SimpleNamespace(
        desktop_window_exists=lambda: exists, desktop_window_is_own_launch=lambda: False,
        desktop_stop_client=Mock(return_value=stop_ok),
    )
    task._desktop_start_and_login = Mock()
    if not stop_ok:
        with pytest.raises(RequestHumanTakeover):
            task._desktop_restart_and_login()
        task._desktop_start_and_login.assert_not_called()
    else:
        task._desktop_restart_and_login()
        task._desktop_start_and_login.assert_called_once_with()
    assert task.device.desktop_stop_client.call_count == int(exists)


@pytest.mark.parametrize('command', ['Restart', 'RealmRaid'])
def test_missing_prescreenshot_allows_only_restart_to_execute(monkeypatch, command):
    script = object.__new__(script_module.Script)
    script.instance_guard = None
    script._try_acquire_queue_token = Mock(return_value=True)
    script.device = SimpleNamespace(screenshot=Mock(side_effect=GameNotRunningError('closed')))
    script.config = SimpleNamespace(task_call=Mock())
    script.exception_handler = Mock()
    run = Mock(side_effect=TaskEnd)
    loader = Mock(return_value=SimpleNamespace(ScriptTask=lambda **kw: SimpleNamespace(run=run)))
    monkeypatch.setattr(script_module, 'load_module', loader)
    assert script.run(command) is True
    assert run.call_count == int(command == 'Restart')
    assert script.config.task_call.call_count == int(command != 'Restart')


def test_enabled_restart_option_uses_window_recovery():
    task = object.__new__(ScriptTask)
    task.device = SimpleNamespace(is_desktop=True)
    task.config = SimpleNamespace(
        script=SimpleNamespace(desktop=SimpleNamespace(restart_when_window_exists=True)),
        restart=SimpleNamespace(harvest_config=SimpleNamespace(enable_ap=False)),
    )
    task._desktop_restart_and_login = Mock()
    task.set_next_run = Mock()
    task.app_restart()
    task._desktop_restart_and_login.assert_called_once_with()
    task.set_next_run.assert_called_once_with(task='Restart', success=True, finish=True, server=True)
