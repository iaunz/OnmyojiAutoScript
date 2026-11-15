"""Replay donation rewards and bounded mission switching without a device."""
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from module.base import timer
from module.device.device import Device
from tasks.CollectiveMissions.script_task import MC, ScriptTask


class DonationReplay(ScriptTask):
    def __init__(self, frames):
        self.frames = iter([(0, 'I_CM_PRESENT'), (0, ''), (0, 'I_CM_MATTER')] + frames)
        self.now = 100
        self.frame = ''
        self.clicks = []
        self.rewards = 0
        self.finalized = False
        self.device = SimpleNamespace(image=None)
        self.config = SimpleNamespace(script=SimpleNamespace(
            device=SimpleNamespace(control_method='window_message')))
        for name in ('O_CM_1_MATTER', 'O_CM_2_MATTER', 'O_CM_3_MATTER', 'O_CM_4_MATTER'):
            setattr(self, name, SimpleNamespace(ocr=lambda image: (0, 100, 100)))

    def screenshot(self):
        elapsed, self.frame = next(self.frames)
        self.now += elapsed

    def appear(self, asset, **kwargs):
        return self.frame and asset is getattr(self, self.frame, None)

    def appear_then_click(self, asset, **kwargs):
        if self.appear(asset):
            self.clicks.append(self.frame)
            return True
        return False

    def ui_reward_appear_click(self, final):
        if final:
            self.finalized = True
            return False
        if self.frame == 'reward':
            self.rewards += 1
            return True
        return False


@pytest.mark.parametrize('frames,rewards,clicks', [
    ([(1, ''), (5, '')], 0, []),
    ([(1, 'reward'), (6, '')], 1, []),
    ([(4, 'I_CM_PRESENT'), (4, 'I_CM_REWARDS'), (4, 'reward'),
      (4, 'I_CM_REWARDS'), (4, 'reward'), (1, '')],
     2, ['I_CM_PRESENT', 'I_CM_REWARDS', 'I_CM_REWARDS']),
])
def test_donation_handles_missing_single_and_double_rewards(monkeypatch, frames, rewards, clicks):
    task = DonationReplay(frames)
    monkeypatch.setattr(timer.time, 'time', lambda: task.now)
    assert task._donate(0) is True
    assert task.rewards == rewards
    assert task.clicks == clicks
    assert task.finalized


class MissionReplay(ScriptTask):
    def __init__(self, target_at):
        self.target_at = target_at
        self.clicks = 0
        self.device = object.__new__(Device)
        self.device.click_record = deque(maxlen=15)
        self.device.image = None
        self.I_CM_SWITCH = SimpleNamespace(match_brightness=lambda image: True,
                                          match_mean_color=lambda image, **kwargs: True)
        self.screenshot = Mock()

    def detect_one(self, *args):
        return MC.BL if self.clicks == self.target_at else MC.UNKNOWN

    def appear_then_click(self, asset, **kwargs):
        self.device.click_record_add('mission switch')
        self.device.click_record_check()
        self.clicks += 1
        return True


@pytest.mark.parametrize('target_at,result,clicks', [(18, True, 18), (None, False, 21)])
def test_switch_reaches_target_or_retry_limit_with_real_click_guard(target_at, result, clicks):
    task = MissionReplay(target_at)
    assert task.select_mission(MC.BL) is result
    assert task.clicks == clicks
