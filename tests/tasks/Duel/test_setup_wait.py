from types import SimpleNamespace

import pytest

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base import timer
from tasks.Duel.script_task import ScriptTask


class DuelReplay(ScriptTask):
    def __init__(self, monkeypatch, auto_after):
        self.now = 100.0
        self.frames = 0
        self.interval_timer = {}
        self.clicks = []
        self.auto_after = auto_after
        self.setup_finished = False
        self.resets = []
        self.conf = SimpleNamespace(duel_config=SimpleNamespace(green_enable=False, green_mark=None))
        self.device = SimpleNamespace(image=set(), click=self.record_click)
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))
        monkeypatch.setattr(RuleImage, 'match', lambda asset, image, **kw: asset.name in image)
        monkeypatch.setattr(RuleOcr, 'ocr', lambda asset, image, **kw: asset.keyword if asset.name in image else '')

    def screenshot(self):
        self.frames += 1
        assert self.frames < 70, 'Duel setup never returned to the battle loop'
        self.now += 1
        if self.setup_finished:
            self.device.image = {self.I_CHECK_DUEL.name, self.I_D_HELP.name}
        else:
            self.device.image = {self.O_D_HAND.name}
            if self.auto_after is not None and len(self.clicks) >= self.auto_after:
                self.device.image.add(self.O_D_AUTO.name)

    def record_click(self, x, y, control_name):
        assert control_name == self.O_D_HAND.name
        self.clicks.append(self.now)

    def check_and_get_reward(self):
        pass

    def is_battle_win(self):
        return False

    def is_battle_lose(self):
        return False

    def green_mark(self, *args):
        self.setup_finished = True

    def reset_device(self, reason):
        self.resets.append(reason)


@pytest.mark.parametrize('auto_after', [None, 1], ids=['timeout', 'auto-appears'])
def test_setup_returns_to_battle_loop_with_bounded_clicks(monkeypatch, auto_after):
    task = DuelReplay(monkeypatch, auto_after)
    assert task.wait_battle() is None
    assert task.setup_finished
    assert task.resets == ['BATTLE_STATUS_S']
    if auto_after is None:
        assert 45 <= task.now - 100 <= 48
        assert 1 < len(task.clicks) <= 8
        assert all(later - earlier >= 6 for earlier, later in zip(task.clicks, task.clicks[1:]))
    else:
        assert task.now - 100 < 10
        assert len(task.clicks) == 1
