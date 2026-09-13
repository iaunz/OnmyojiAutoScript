from types import SimpleNamespace

import pytest

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base import timer
from tasks.Restart.login import LoginHandler


class LoginReplay(LoginHandler):
    """Run the real login loop with deterministic screenshots and a fake clock."""

    def __init__(self, monkeypatch, next_screen):
        self.interval_timer = {}
        self.now = 100.0
        self.frames = 0
        self.clicks = []
        self.next_screen = next_screen
        self.device = SimpleNamespace(
            image=set(),
            screenshot=self.take_screenshot,
            click=self.record_click,
            stuck_record_add=lambda name: None,
            get_orientation=lambda: None,
            check_screen_size_sample=lambda: True,
        )
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))
        monkeypatch.setattr(
            RuleImage, 'match', lambda asset, image, **kwargs: asset.name in image
        )

        def ocr(asset, image, **kwargs):
            if asset.name not in image:
                return (0, 0, 0, 0) if asset is self.O_LOGIN_SPECIFIC_SERVE else ''
            if asset is self.O_LOGIN_SPECIFIC_SERVE:
                return (110, 120, 100, 30)
            return asset.keyword

        monkeypatch.setattr(RuleOcr, 'ocr', ocr)

    def take_screenshot(self):
        self.frames += 1
        assert self.frames <= 80, 'Login did not reach the courtyard'
        self.now += 0.5
        self.device.image = {asset.name for asset in self.next_screen(self)}

    def record_click(self, x, y, control_name=None):
        self.clicks.append((control_name, self.frames, self.now))

    def courtyard(self):
        return [self.I_BUFF_1, self.I_MAIN_GOTO_SHIKIGAMI_RECORDS]

    def login_screen(self, alternate=False):
        button = self.O_LOGIN_ENTER_GAME if alternate else self.O_LOGIN_ENTER_GAME_ORIGIN
        return [self.I_LOGIN_8, button]


@pytest.mark.parametrize('alternate_on_retry', [False, True])
def test_ignored_enter_game_click_is_retried_on_a_new_frame(monkeypatch, alternate_on_retry):
    def next_screen(task):
        if len(task.clicks) >= 2:
            return task.courtyard()
        return task.login_screen(alternate=bool(task.clicks) and alternate_on_retry)

    task = LoginReplay(monkeypatch, next_screen)

    assert task._app_handle_login() is True
    assert len(task.clicks) == 2
    first, second = task.clicks
    assert first[0] == task.O_LOGIN_ENTER_GAME_ORIGIN.name
    expected_retry = task.O_LOGIN_ENTER_GAME if alternate_on_retry else task.O_LOGIN_ENTER_GAME_ORIGIN
    assert second[0] == expected_retry.name
    assert second[1] > first[1]
    assert second[2] - first[2] >= 3


def test_direct_courtyard_entry_does_not_wait_for_character_selection(monkeypatch):
    task = LoginReplay(
        monkeypatch,
        lambda task: task.courtyard() if task.clicks else task.login_screen(),
    )

    assert task._app_handle_login() is True
    assert len(task.clicks) == 1
    # The courtyard is immediately available; only its stability check is needed.
    assert task.now - task.clicks[0][2] < 3


def test_character_selection_is_handled_after_enter_game(monkeypatch):
    def next_screen(task):
        clicked = [click[0] for click in task.clicks]
        if task.C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR.name in clicked:
            return task.courtyard()
        if task.O_LOGIN_ENTER_GAME_ORIGIN.name in clicked:
            return [task.I_LOGIN_SPECIFIC_SERVE, task.O_LOGIN_SPECIFIC_SERVE]
        return task.login_screen()

    task = LoginReplay(monkeypatch, next_screen)

    assert task._app_handle_login() is True
    assert [click[0] for click in task.clicks] == [
        task.O_LOGIN_ENTER_GAME_ORIGIN.name,
        task.O_LOGIN_SPECIFIC_SERVE.name,
        task.C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR.name,
    ]


def test_server_selection_is_left_before_processing_a_new_login_frame(monkeypatch):
    def next_screen(task):
        if not task.clicks:
            return [task.I_CHARACTARS, *task.login_screen()]
        if len(task.clicks) == 1:
            return task.login_screen()
        return task.courtyard()

    task = LoginReplay(monkeypatch, next_screen)

    assert task._app_handle_login() is True
    assert len(task.clicks) == 2
    assert task.clicks[1][0] == task.O_LOGIN_ENTER_GAME_ORIGIN.name
    assert task.clicks[1][1] > task.clicks[0][1]


def test_loading_frames_do_not_trigger_another_enter_game_click(monkeypatch):
    def next_screen(task):
        if not task.clicks:
            return task.login_screen()
        if task.now - task.clicks[0][2] < 6:
            return []
        return task.courtyard()

    task = LoginReplay(monkeypatch, next_screen)

    assert task._app_handle_login() is True
    assert len(task.clicks) == 1
