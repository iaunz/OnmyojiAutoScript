from types import SimpleNamespace

import pytest

from module.base import timer
from tasks.Delegation.script_task import ScriptTask


@pytest.mark.parametrize('mode', ['cancel', 'back', 'entry'])
def test_entry_and_back_waits_are_bounded_and_cancel_has_priority(monkeypatch, mode):
    now = [100.0]
    monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: now[0]))
    task = object.__new__(ScriptTask)
    task.O_D_NAME = SimpleNamespace(keyword='')
    clicks, waits, name_intervals = [], [], []

    def screenshot():
        now[0] += 1
        assert now[0] < 125, 'delegation entry/back loop did not terminate'

    def appear(asset, **kwargs):
        return ((asset is task.I_UI_CANCEL and mode == 'cancel')
                or (asset is task.I_D_BACK and mode in ('cancel', 'back')))

    def click(asset, **kwargs):
        clicks.append(asset)
        return True

    task.screenshot = screenshot
    task.appear = appear
    task.click = click
    assets = [task.I_UI_CANCEL, task.I_D_BACK]
    task.device = SimpleNamespace(click=lambda x, y, control_name: click(
        next(asset for asset in assets if asset.name == control_name)))
    task.interval_timer = {}
    task.ocr_appear = lambda *args: True
    task.ocr_appear_click = lambda asset, interval: name_intervals.append(interval) or True
    task.wait_until_appear = lambda asset, wait_time: waits.append((asset, wait_time))
    assert task.delegate_one('画') is False
    if mode == 'cancel':
        assert clicks and all(asset is task.I_UI_CANCEL for asset in clicks)
        assert not name_intervals
    elif mode == 'back':
        assert clicks and all(asset is task.I_D_BACK for asset in clicks)
        assert waits == [(task.I_REWARDS_MIN, 3)]
    else:
        assert not clicks
        assert name_intervals and all(value == 3 for value in name_intervals)


def test_start_wait_is_bounded_when_prepare_never_disappears(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: now[0]))
    task = object.__new__(ScriptTask)
    task.O_D_NAME = SimpleNamespace(keyword='')

    def screenshot():
        now[0] += 1
        assert now[0] < 125, 'delegation start loop did not terminate'

    task.screenshot = screenshot
    task.ocr_appear = lambda *args: True
    task.appear = lambda *args, **kwargs: True
    task.click = lambda *args, **kwargs: True
    task.delegate_one('画')
    assert 115 <= now[0] < 125
