import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tasks.Component.GeneralBattle.battle_wait import (
    BattleResult, BattleWait, BattleWaitPlan, HookSignal, OptionSuccessDefault,
    PerBattleSuccess, runtime,
)


@pytest.mark.parametrize('overflow_on_entry', [False, True])
def test_overflow_is_dismissed_before_settlement_completes(monkeypatch, overflow_on_entry):
    monkeypatch.setattr(runtime, 'task_owner', None)
    monkeypatch.setattr(runtime, 'pub_ctx', None)
    monkeypatch.setattr(runtime, 'pri_ctx', {})

    class Replay(BattleWait):
        def __init__(self):
            self.overflow = overflow_on_entry
            self.inject_overflow = not overflow_on_entry
            self.reward = True
            self.clicks = []
            self.device = SimpleNamespace(click=self.device_click)

        def device_click(self, x, y, control_name):
            assert control_name == self.I_OVER_GHOST.name
            return self.click(self.I_OVER_GHOST)

        def screenshot(self):
            if self.inject_overflow:
                self.overflow = True
                self.inject_overflow = False

        def appear(self, asset, **kwargs):
            if asset is self.I_OVER_GHOST:
                return self.overflow
            return asset is self.I_REWARD and self.reward

        def click(self, asset, **kwargs):
            self.clicks.append(asset)
            assert asset is self.I_OVER_GHOST, 'unexpected click behind overflow dialog'
            self.overflow = False
            self.reward = False
            return True

    battle = Replay()
    runtime.update_options({}, plan=BattleWaitPlan())
    if not overflow_on_entry:
        assert battle._bw_success_default() == HookSignal.CONTINUE
        assert battle.clicks == []
        assert runtime.pub_ctx.per_battle.success != BattleResult.SUCCESS
    assert battle._bw_interrupt_default() == HookSignal.CONTINUE
    assert battle.clicks == [battle.I_OVER_GHOST]
    assert runtime.pub_ctx.per_battle.success != BattleResult.SUCCESS
    # A later reward frame can now complete through the usual success path.
    battle.reward = True
    battle.screenshot = lambda: setattr(battle, 'reward', False)
    battle._bw_success_default()
    assert runtime.pub_ctx.per_battle.success == BattleResult.SUCCESS


def test_overflow_cleanup_button_is_excluded_and_has_persistent_metadata():
    owner = object.__new__(BattleWait)
    rule = PerBattleSuccess.reward_exclude_click(owner, OptionSuccessDefault().excludes_2)
    x, y = owner.C_OVERFLOW_GHOST.center
    assert rule._is_excluded(x, y)
    rows = json.loads(Path('tasks/Component/GeneralBattle/gb/click.json').read_text(encoding='utf-8'))
    row, = [row for row in rows if row['itemName'] == 'overflow_ghost']
    for field, roi in [('roiFront', owner.C_OVERFLOW_GHOST.roi_front),
                       ('roiBack', owner.C_OVERFLOW_GHOST.roi_back)]:
        assert tuple(map(int, row[field].split(','))) == roi
