"""Replay mail controls from the screenshots reported on 2026-10-11."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from module.base import timer
from module.exception import GameStuckError
from tasks.Restart.login import LoginHandler


@pytest.fixture
def mail_screens():
    screens = {}
    for name in ('mailbox', 'mail_claim', 'mail_reward'):
        path = Path(__file__).with_name('fixtures') / f'{name}.png'
        screens[name] = cv2.cvtColor(
            cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR),
            cv2.COLOR_BGR2RGB,
        )
    screens['empty'] = screens['mailbox'].copy()
    screens['empty'][551:695, 28:170] = 0
    screens['closed'] = np.zeros_like(screens['mailbox'])
    return screens


class MailReplay(LoginHandler):
    def __init__(self, monkeypatch, screens, *, screen='mailbox', frame_seconds=0.5,
                 ignored_confirms=0, reward_delay=0):
        self.interval_timer = {}
        self.now = 100.0
        self.frames = 0
        self.clicks = []
        self.screen = screen
        self.screens = screens
        self.frame_seconds = frame_seconds
        self.ignored_confirms = ignored_confirms
        self.reward_delay = reward_delay
        self.reward_at = None
        self.device = SimpleNamespace(image=screens[screen], click=self.record_click)
        for name in (
            'I_HARVEST_MAIL', 'I_HARVEST_MAIL_COPY', 'I_READ_ALL_MAIL',
            'I_HARVEST_MAIL_ALL', 'I_HARVEST_MAIL_CONFIRM', 'I_MAIL_RED_POINT',
            'I_MAIL_REWARD', 'I_UI_REWARD', 'I_UI_AWARD', 'I_LOGIN_RED_CLOSE',
        ):
            if hasattr(self, name):
                setattr(self, name, deepcopy(getattr(self, name)))
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))

    def screenshot(self):
        self.frames += 1
        assert self.frames <= 160, 'Mail collection did not finish'
        self.now += self.frame_seconds
        if self.reward_at is not None and self.now >= self.reward_at:
            self.screen = 'mail_reward'
            self.reward_at = None
        self.device.image = self.screens[self.screen]

    def record_click(self, x, y, control_name):
        self.clicks.append(control_name)
        if control_name == self.I_HARVEST_MAIL_ALL.name:
            assert self.screen == 'mailbox', 'Clicked claim behind a popup'
            self.screen = 'mail_claim'
        elif control_name == self.I_HARVEST_MAIL_CONFIRM.name:
            assert self.screen == 'mail_claim'
            assert 673 <= x < 854 and 543 <= y < 609
            if self.ignored_confirms:
                self.ignored_confirms -= 1
            elif self.reward_delay:
                self.screen = 'empty'
                self.reward_at = self.now + self.reward_delay
            else:
                self.screen = 'mail_reward'
        elif control_name == self.I_READ_ALL_MAIL.name:
            assert self.screen in ('mailbox', 'empty'), 'Clicked read behind a popup'
        elif control_name == self.I_LOGIN_RED_CLOSE.name:
            assert self.screen == 'empty', 'Closed before collecting rewards'
            assert self.reward_at is None, 'Closed before the reward arrived'
            self.screen = 'closed'
        else:
            assert self.screen == 'mail_reward'
            assert control_name in (self.I_UI_REWARD.name, self.I_MAIL_REWARD.name)
            self.screen = 'empty'


@pytest.mark.parametrize('frame_seconds', [0.5, 2.0])
def test_mail_is_claimed_before_reading_even_with_slow_screenshots(
        monkeypatch, mail_screens, frame_seconds):
    task = MailReplay(monkeypatch, mail_screens, frame_seconds=frame_seconds)

    assert task.harvest_mail() is True
    assert task.screen == 'closed'
    assert task.clicks == [
        task.I_HARVEST_MAIL_ALL.name, task.I_HARVEST_MAIL_CONFIRM.name,
        task.I_MAIL_REWARD.name, task.I_READ_ALL_MAIL.name, task.I_LOGIN_RED_CLOSE.name,
    ]


@pytest.mark.parametrize('screen', ['mail_claim', 'mail_reward'])
def test_existing_mail_popup_is_finished_before_closing(monkeypatch, mail_screens, screen):
    task = MailReplay(monkeypatch, mail_screens, screen=screen)

    assert task.harvest_mail() is True
    assert task.screen == 'closed'
    assert task.I_MAIL_REWARD.name in task.clicks
    assert task.I_HARVEST_MAIL_ALL.name not in task.clicks


def test_ignored_confirmation_is_retried_without_clicking_background(monkeypatch, mail_screens):
    task = MailReplay(monkeypatch, mail_screens, ignored_confirms=1, frame_seconds=0.25)

    assert task.harvest_mail() is True
    assert task.screen == 'closed'
    assert task.clicks.count(task.I_HARVEST_MAIL_CONFIRM.name) == 2
    assert task.clicks.count(task.I_HARVEST_MAIL_ALL.name) == 1


def test_delayed_reward_is_collected_after_confirmation(monkeypatch, mail_screens):
    task = MailReplay(monkeypatch, mail_screens, reward_delay=4)

    assert task.harvest_mail() is True
    assert task.screen == 'closed'
    assert task.I_MAIL_REWARD.name in task.clicks


def test_empty_mailbox_is_read_once_and_closed(monkeypatch, mail_screens):
    task = MailReplay(monkeypatch, mail_screens, screen='empty')

    assert task.harvest_mail() is True
    assert task.clicks == [task.I_READ_ALL_MAIL.name, task.I_LOGIN_RED_CLOSE.name]


def test_stuck_confirmation_times_out_without_closing_behind_it(monkeypatch, mail_screens):
    task = MailReplay(monkeypatch, mail_screens, ignored_confirms=100)

    with pytest.raises(GameStuckError, match='mail'):
        task.harvest_mail()

    assert task.I_LOGIN_RED_CLOSE.name not in task.clicks


def test_no_mail_does_not_click(monkeypatch, mail_screens):
    task = MailReplay(monkeypatch, mail_screens, screen='closed')

    assert task.harvest_mail() is False
    assert task.clicks == []
