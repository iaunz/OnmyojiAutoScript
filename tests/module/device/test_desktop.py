from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from module.device.method import desktop_impl as desktop
from module.device.desktop_device import DesktopDevice
from module.device.device import Device
from module.device.platform2 import Platform
from module.atom import image
from module.exception import GameNotRunningError, RequestHumanTakeover
from tasks.Restart.script_task import ScriptTask
from tasks.Script.config import Script


def test_existing_configs_default_to_emulator():
    assert Script.model_validate({'device': {'serial': '127.0.0.1:16384'}}).desktop.enable is False


def test_rebuilt_window_refreshes_screenshot_and_input_caches(monkeypatch):
    window = desktop.DesktopWindow()
    window.root_handle = '123'
    window.root_handle_num = 11
    window.screenshot_handle_num = 11
    window.screenshot_size = (1280, 720)
    window.control_handle_list = [11]
    monkeypatch.setattr(desktop, 'find_desktop_window_by_pid', lambda *args: 22)
    assert window.desktop_window_exists()
    assert window.root_handle_num == 22
    assert 'screenshot_handle_num' not in window.__dict__
    assert 'control_handle_list' not in window.__dict__


def test_missing_main_process_does_not_hide_failed_launcher_cleanup(monkeypatch):
    window = desktop.DesktopWindow()
    window.root_handle = '123'
    window.root_handle_num = 0
    window.desktop_profile_dir = lambda: None
    window._desktop_kill_spawned_leftovers = Mock(return_value=False)
    monkeypatch.setattr(desktop, 'desktop_pid_alive', lambda pid: False)
    monkeypatch.setattr(desktop, 'desktop_keep_screen_on', lambda enable: None)
    assert window.desktop_stop_client() is False


@pytest.mark.parametrize('job', [0, 99])
def test_isolated_spawn_never_claims_an_unrelated_new_window(monkeypatch, tmp_path, job):
    now = [100.0]
    monkeypatch.setattr(desktop, 'time', SimpleNamespace(
        time=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds)))
    other = dict(pid=456, hwnd=33)
    monkeypatch.setattr(desktop, 'list_desktop_windows',
                        lambda: [] if now[0] == 100 else [other])
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(pid=123))
    monkeypatch.setattr(desktop, '_desktop_attach_job', lambda pid: job)
    monkeypatch.setattr(desktop, '_desktop_job_member_pids', lambda handle: set())
    monkeypatch.setattr(desktop, '_desktop_pid_under_root', lambda *args: True)
    monkeypatch.setattr(desktop, '_desktop_best_window', lambda pid, hwnd: hwnd)
    monkeypatch.setattr(desktop.ctypes, 'windll', SimpleNamespace(kernel32=SimpleNamespace(CloseHandle=lambda handle: None)))
    bound = Mock()
    pid, spawned = desktop.desktop_spawn_client('game.exe', str(tmp_path), tmp_path / 'account', timeout=4, on_bound=bound)
    assert pid == 0
    assert spawned == {123}
    bound.assert_not_called()


@pytest.mark.parametrize('cleanup_succeeds', [True, False])
def test_failed_launch_cleans_each_attempt_before_retry(monkeypatch, cleanup_succeeds):
    window = desktop.DesktopWindow()
    window.desktop_resolve_install_root = lambda: 'game'
    window.desktop_profile_dir = lambda: None
    calls, killed, alive = [], [], set()
    monkeypatch.setattr(desktop, 'desktop_game_exe', lambda root: 'game.exe')

    def spawn(*args, **kwargs):
        pid = 100 + len(calls)
        calls.append(pid)
        alive.add(pid)
        return 0, {pid}

    def cleanup(pids):
        killed.append(set(pids))
        if cleanup_succeeds:
            alive.difference_update(pids)

    monkeypatch.setattr(desktop, 'desktop_spawn_client', spawn)
    monkeypatch.setattr(desktop, 'desktop_pid_alive', lambda pid: pid in alive)
    window._desktop_kill_pids = cleanup
    assert window.launch_desktop_client(timeout=1) is False
    assert len(calls) == (2 if cleanup_succeeds else 1)
    assert killed == [{pid} for pid in calls]


def test_emulator_initialization_resets_desktop_matching_padding(monkeypatch):
    task = object.__new__(Device)
    task.is_desktop = False
    task.config = SimpleNamespace(script=SimpleNamespace(device=SimpleNamespace(
        emulatorinfo_type='MuMuPlayer', screenshot_method='adb')))
    task.screenshot_interval_set = lambda: None
    monkeypatch.setattr(Platform, '__init__', lambda *args, **kwargs: None)
    monkeypatch.setattr(image, 'ROI_MATCH_PAD', 2)
    Device.__init__(task)
    assert image.ROI_MATCH_PAD == 0


def test_live_process_waits_for_window_without_spawning(monkeypatch):
    import module.device.desktop_device as lifecycle
    task = DesktopDevice()
    task.desktop_pid = lambda: 123
    task.desktop_window_exists = lambda: False
    task._desktop_wait_window_ready = Mock(return_value=False)
    task.launch_desktop_client = Mock()
    monkeypatch.setattr(lifecycle, 'desktop_pid_alive', lambda pid: True)
    assert task._desktop_ensure_launched() is False
    task.launch_desktop_client.assert_not_called()


def test_profile_without_state_cannot_adopt_other_accounts(monkeypatch, tmp_path):
    window = desktop.DesktopWindow()
    window.desktop_profile_dir = lambda: tmp_path
    monkeypatch.setattr(desktop, 'list_desktop_windows', Mock(side_effect=AssertionError('must not enumerate other accounts')))
    assert window._desktop_locate_window() == (None, 0)


@pytest.mark.parametrize('cleanup_succeeds', [True, False])
def test_restart_stops_after_bounded_failed_logins(cleanup_succeeds):
    task = object.__new__(ScriptTask)
    task.device = SimpleNamespace(app_start=Mock(), desktop_stop_client=Mock(return_value=cleanup_succeeds))
    task.app_handle_login = Mock(side_effect=GameNotRunningError('no window'))
    with pytest.raises(RequestHumanTakeover):
        task._desktop_start_and_login()
    assert task.device.app_start.call_count == (3 if cleanup_succeeds else 1)


def test_profile_environment_does_not_mutate_parent(monkeypatch, tmp_path):
    monkeypatch.setenv('USERPROFILE', 'parent-home')
    env = desktop.desktop_profile_env(tmp_path)
    assert env['USERPROFILE'] == str(tmp_path / 'home')
    assert desktop.os.environ['USERPROFILE'] == 'parent-home'
    desktop.desktop_write_instance_state(tmp_path, 123)
    assert desktop.desktop_read_instance_state(tmp_path) == {'pid': 123}
    desktop.desktop_clear_instance_state(tmp_path)
    assert desktop.desktop_read_instance_state(tmp_path) == {}


@pytest.mark.parametrize('job_pids,window_pid', [(set(), 123), ({123, 456}, 456)])
def test_isolated_spawn_accepts_owned_window(monkeypatch, tmp_path, job_pids, window_pid):
    now = [100.0]
    monkeypatch.setattr(desktop, 'time', SimpleNamespace(
        time=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds)))
    monkeypatch.setattr(desktop, 'list_desktop_windows', lambda: [dict(pid=window_pid, hwnd=22)])
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(pid=123))
    monkeypatch.setattr(desktop, '_desktop_attach_job', lambda pid: 99)
    monkeypatch.setattr(desktop, '_desktop_job_member_pids', lambda handle: job_pids)
    monkeypatch.setattr(desktop, '_desktop_pid_under_root', lambda *args: True)
    monkeypatch.setattr(desktop, '_desktop_best_window', lambda pid, hwnd: hwnd)
    monkeypatch.setattr(desktop.ctypes, 'windll', SimpleNamespace(kernel32=SimpleNamespace(CloseHandle=lambda handle: None)))
    bound = Mock()
    pid, spawned = desktop.desktop_spawn_client('game.exe', str(tmp_path), tmp_path / 'account', timeout=4, on_bound=bound)
    assert pid == window_pid
    assert {123, window_pid}.issubset(spawned)
    bound.assert_called_once_with(window_pid, 22)
