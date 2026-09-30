"""Replay the real weekly storage workflow without a device or OCR engine."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from module.exception import GameStuckError
from tasks.WeeklyTrifles import script_task
from tasks.WeeklyTrifles.script_task import ScriptTask


@pytest.fixture(autouse=True)
def advance_time_without_sleeping(monkeypatch):
    clock = [0.0]

    class ReplayTimer:
        def __init__(self, limit):
            self.limit = limit

        def start(self):
            self.deadline = clock[0] + self.limit
            return self

        def reached(self):
            return clock[0] >= self.deadline

    def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(script_task, 'Timer', ReplayTimer)
    monkeypatch.setattr(script_task, 'sleep', sleep)


class StorageReplay(ScriptTask):
    def __init__(self, frames, *, failed_save_clicks=0, tickets=10, cost=5,
                 menu_opens=True):
        # BaseTask initialization requires a running emulator; keep its workflow.
        self.frames = list(frames)
        self.frame = set()
        self.stage = None
        self.menu_opens = menu_opens
        self.failed_save_clicks = failed_save_clicks
        self.save_attempts = 0
        self.clicks = []
        self.destinations = []
        self.screenshots = 0
        self.device = SimpleNamespace(image=None)
        self.O_WT_LUCKY_TICKETS = SimpleNamespace(ocr=Mock(return_value=(tickets, 0, tickets)))
        self.O_WT_SAVE_COST = SimpleNamespace(ocr=Mock(return_value=cost))
        self.config = SimpleNamespace(weekly_trifles=SimpleNamespace(trifles=SimpleNamespace(
            share_collect=False, share_area_boss=False, share_secret=False,
            save_touch_fish=True, broken_amulet=0,
        )))
        self.set_next_run = Mock()

    def ui_get_current_page(self):
        pass

    def ui_goto(self, page):
        self.destinations.append(page)
        self.stage = page
        return True

    def screenshot(self):
        self.screenshots += 1
        assert self.screenshots < 200, 'Storage workflow did not respect its timeout'
        if self.stage is script_task.page_guild:
            self.frame = {'I_WT_FOLD_WINDOW' if self.menu_opens else 'I_WT_OPEN_FOLD_WINDOW'}
        elif self.frames:
            self.frame = set(self.frames.pop(0))
        self.device.image = frozenset(self.frame)

    def appear(self, asset, **kwargs):
        return any(asset is getattr(self, name) for name in self.frame)

    def appear_then_click(self, asset, **kwargs):
        if not self.appear(asset):
            return False
        if asset is self.I_WT_SAVE_ALL:
            self.save_attempts += 1
            if self.failed_save_clicks:
                self.failed_save_clicks -= 1
                return False
        self.clicks.append(asset)
        return True

    def click(self, asset, **kwargs):
        self.clicks.append(asset)
        return True


def test_storage_dismisses_obscuring_popups_before_reading_tickets():
    task = StorageReplay([
        {'I_WT_LAST_SAVE'},
        {'I_WT_HAPPY_GET'},
        {'I_WT_SAVE_ALL'},
        {'I_WT_TF_CONFIRM'},
        {'I_WT_TF_SAVE_SUCCESS'},
    ])

    task._save_touch_fish()

    task.O_WT_LUCKY_TICKETS.ocr.assert_called_once_with(frozenset({'I_WT_SAVE_ALL'}))
    assert task.I_WT_HAPPY_GET in task.clicks
    assert task.I_WT_TF_CONFIRM in task.clicks
    assert task.save_attempts == 1
    assert task.destinations[-1] is script_task.page_main


def test_storage_retries_a_save_button_that_was_not_clicked():
    task = StorageReplay([
        {'I_WT_SAVE_ALL'}, {'I_WT_SAVE_ALL'},
        {'I_WT_TF_CONFIRM'}, {'I_WT_TF_SAVE_SUCCESS'},
    ], failed_save_clicks=1)

    task._save_touch_fish()

    assert task.save_attempts == 2
    assert task.destinations[-1] is script_task.page_main


@pytest.mark.parametrize('stuck_frame', [
    {'I_WT_LAST_SAVE'}, {'I_WT_HAPPY_GET'}, {'I_WT_TF_CONFIRM'}, set(),
])
def test_storage_timeout_cannot_mark_the_week_complete(stuck_frame):
    task = StorageReplay([stuck_frame])

    with pytest.raises(GameStuckError, match='Touch fish save'):
        task.run()

    task.set_next_run.assert_not_called()
    assert task.destinations[-1] is script_task.page_touch_fish


def test_guild_menu_has_a_bounded_wait():
    task = StorageReplay([], menu_opens=False)

    with pytest.raises(GameStuckError, match='guild menu'):
        task._save_touch_fish()

    assert script_task.page_touch_fish not in task.destinations


def test_already_stored_week_needs_no_ocr_or_new_save():
    task = StorageReplay([{'I_WT_TF_SAVE_SUCCESS'}])

    task._save_touch_fish()

    task.O_WT_LUCKY_TICKETS.ocr.assert_not_called()
    assert task.save_attempts == 0
    assert task.destinations[-1] is script_task.page_main


def test_insufficient_tickets_does_not_click_save():
    task = StorageReplay([{'I_WT_SAVE_ALL'}], tickets=1, cost=5)

    task._save_touch_fish()

    assert task.save_attempts == 0
    assert task.destinations[-1] is script_task.page_main
