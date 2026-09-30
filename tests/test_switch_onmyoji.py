"""SwitchOnmyoji must have a bounded exit path.

Both loops in `SwitchOnmyoji.switch_role` used to be unconditional `while True`.
When the onmyoji/hero tab cannot be reached (stale asset coordinates after a
game UI update, emulator showing a different page, ...), they kept clicking
forever until the global `GameStuckError` watchdog fired roughly two minutes
later, discarding all context about what actually went wrong.

These tests pin the exit conditions: a loop that never finds its target has to
raise a named, catchable `ScriptError` instead of spinning, and the happy path
must keep working unchanged.
"""
import pytest
from types import SimpleNamespace

import module.base.timer as timer_module
from module.exception import ScriptError
from tasks.Component.SwitchOnmyoji.config import Onmyoji
from tasks.Component.SwitchOnmyoji.switch_onmyoji import SwitchOnmyoji


@pytest.fixture
def clock(monkeypatch):
    """Advance only when a screenshot is taken; never depend on wall time."""
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(timer_module, 'time', SimpleNamespace(time=lambda: clock.now))
    return clock


class ScriptedSwitch(SwitchOnmyoji):
    """Double that replays a fixed sequence of `appear` results.

    `screenshot` and every click are no-ops, so the test exercises the real
    loop control flow of `switch_role` without a Config, a Device or a game.
    """

    def __init__(self, appear_results, clock, timeout=20):
        # deliberately skip BaseTask.__init__: it needs a real Config/Device
        self._appear_results = list(appear_results)
        self._appear_calls = 0
        self._clock = clock
        self.switch_clicks = 0
        self.battle_clicks = 0
        self.ui_clicks = 0
        # The fake clock makes both real 20s guards run without waiting.
        self.SWITCH_TAB_TIMEOUT = timeout
        self.SWITCH_BATTLE_TIMEOUT = timeout

    def _next_appear(self, button):
        self._appear_calls += 1
        if not self._appear_results:
            return False
        return self._appear_results.pop(0)

    def screenshot(self):
        self._clock.now += 1

    def appear(self, button, interval=None, **kwargs):
        return self._next_appear(button)

    def appear_then_click(self, button, interval=None, **kwargs):
        self.switch_clicks += 1
        return True

    def click(self, button, interval=None, **kwargs):
        self.battle_clicks += 1
        return True

    def ui_click(self, button1, button2, interval=None, **kwargs):
        self.ui_clicks += 1
        return True


def test_switch_role_raises_when_battle_list_never_appears(clock):
    task = ScriptedSwitch(appear_results=[], clock=clock)

    with pytest.raises(ScriptError, match='cannot reach the role list'):
        task.switch_role(role=None, battle_dict={'x': object()}, check_img=object())

    assert task.switch_clicks == 21
    assert task.battle_clicks == 0


def test_switch_role_raises_when_check_icon_never_appears(clock):
    # battle icon visible, confirm icon never does
    task = ScriptedSwitch(appear_results=[True], clock=clock)

    with pytest.raises(ScriptError, match='cannot select'):
        task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())

    assert task.switch_clicks == 0
    assert task.battle_clicks == 21


def test_switch_role_still_switches_when_the_flow_is_healthy(clock):
    # appear order: battle icon, then confirm icon -> no extra clicks needed
    task = ScriptedSwitch(appear_results=[True, True], clock=clock)

    task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())

    assert task.switch_clicks == 0
    assert task.battle_clicks == 0
    assert task.ui_clicks == 0


def test_switch_role_clicks_the_battle_icon_when_confirm_icon_is_absent(clock):
    # appear order: battle icon, not-confirm, battle icon -> ui_click back path
    task = ScriptedSwitch(appear_results=[True, False, True], clock=clock)

    task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())

    assert task.switch_clicks == 0
    assert task.ui_clicks == 1


def test_timeouts_are_not_shared_between_instances(clock):
    a = ScriptedSwitch(appear_results=[], clock=clock)
    b = ScriptedSwitch(appear_results=[], clock=clock)

    assert a.SWITCH_TAB_TIMEOUT is not None
    assert b.SWITCH_TAB_TIMEOUT is not None
