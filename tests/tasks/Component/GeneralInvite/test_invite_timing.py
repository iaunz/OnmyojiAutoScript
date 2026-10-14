from types import SimpleNamespace

import pytest

from module.atom.image import RuleImage
from module.base import timer
from tasks.base_task import BaseTask
from tasks.BondlingFairyland.general_invite import GeneralInvite as BondlingInvite
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber


class InviteReplay(BaseTask):
    """Replay a dialog whose checkbox and confirmation redraw after two seconds."""

    def __init__(self, monkeypatch, checkbox):
        self.interval_timer = {}
        self.now = 100.0
        self.frames = 0
        self.clicks = []
        self.checkbox = checkbox
        self.checked_at = None
        self.closed_at = None
        self.device = SimpleNamespace(image=set(), click=self.record_click)
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))
        monkeypatch.setattr(
            RuleImage, 'match', lambda asset, image, **kwargs: asset.name in image
        )
        self.refresh_image()

    def refresh_image(self):
        if self.closed_at is not None and self.now >= self.closed_at:
            self.device.image = set()
            return
        if self.checked_at is not None and self.now >= self.checked_at:
            self.checkbox = 'checked'
        self.device.image = {self.I_UI_CONFIRM.name}
        if self.checkbox == 'checked':
            self.device.image.add(self.I_UI_CHECK.name)
        elif self.checkbox == 'unchecked':
            self.device.image.add(self.I_UI_UNCHECK.name)

    def screenshot(self):
        self.frames += 1
        assert self.frames < 40, 'Invite dialog did not settle'
        self.now += 0.5
        self.refresh_image()

    def record_click(self, x, y, control_name):
        self.clicks.append(control_name)
        if control_name == self.I_UI_UNCHECK.name:
            assert self.checked_at is None, 'Toggled checkbox again before redraw'
            self.checked_at = self.now + 2
        else:
            assert control_name == self.I_UI_CONFIRM.name
            assert self.checkbox in ('checked', 'absent')
            assert self.closed_at is None, 'Confirmed twice before dialog closed'
            self.closed_at = self.now + 2


@pytest.mark.parametrize('invite', [GeneralInvite, BondlingInvite])
@pytest.mark.parametrize('checkbox', ['unchecked', 'checked', 'absent'])
def test_delayed_invitation_redraw_does_not_repeat_clicks(monkeypatch, invite, checkbox):
    task = InviteReplay(monkeypatch, checkbox)

    assert invite.check_and_invite(task) is True
    assert task.device.image == set()
    expected = [task.I_UI_UNCHECK.name] if checkbox == 'unchecked' else []
    assert task.clicks == [*expected, task.I_UI_CONFIRM.name]


@pytest.mark.parametrize('number', [InviteNumber.ONE, InviteNumber.TWO])
def test_second_friend_is_invited_after_the_first_dialog_settles(monkeypatch, number):
    now = [0.0]
    invitations = []

    def sleep(seconds):
        now[0] += seconds

    def invite_friend(name, find_mode):
        invitations.append((name, now[0]))
        return True

    monkeypatch.setattr('tasks.Component.GeneralInvite.general_invite.sleep', sleep)
    config = InviteConfig(invite_number=number, friend_1='first', friend_2='second')
    GeneralInvite.invite_friends(SimpleNamespace(invite_friend=invite_friend), config)

    assert invitations[0] == ('first', 0.0)
    if number == InviteNumber.TWO:
        assert len(invitations) == 2
        assert invitations[1][0] == 'second'
        assert invitations[1][1] >= 3
    else:
        assert len(invitations) == 1
