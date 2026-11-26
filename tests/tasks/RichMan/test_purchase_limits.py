from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tasks.Component.Buy import buy as buy_module
from tasks.RichMan.guild import Guild


@pytest.mark.parametrize('initial,requested,stock', [(1, 18, 30), (9, 12, 30), (1, 18, 5), (1, 1, 30)])
def test_quantity_selector_stops_at_requested_or_stock(monkeypatch, initial, requested, stock):
    task = object.__new__(buy_module.Buy)
    quantity = initial
    frames = 0
    task.device = SimpleNamespace(image=None, click_record_remove=Mock())
    task.O_BUY_NUMBER = SimpleNamespace(ocr=lambda frame: frame)
    task.appear = lambda rule, **kw: rule is task.I_BUY_PLUS
    task.ui_reward_appear_click = lambda: True

    def screenshot():
        nonlocal frames
        frames += 1
        assert frames < 35
        task.device.image = quantity

    def add(rule, **kw):
        nonlocal quantity
        assert rule is task.I_BUY_ADD
        quantity = min(quantity + 1, stock)
        return True

    task.screenshot = screenshot
    task.appear_then_click = add
    monkeypatch.setattr(buy_module.time, 'sleep', lambda _: None)
    monkeypatch.setattr(buy_module, 'Timer', lambda _: SimpleNamespace(
        start=lambda: None, reached=lambda: True, reset=lambda: None))
    assert task.buy_more(None, requested)
    assert quantity == min(requested, stock)
    if requested - initial >= 7 and stock >= requested:
        task.device.click_record_remove.assert_any_call(task.I_BUY_ADD)


def test_guild_store_leaves_after_eight_actual_swipes(monkeypatch):
    task = object.__new__(Guild)
    task.device = SimpleNamespace(swipe=Mock())
    frames = 0

    def screenshot():
        nonlocal frames
        frames += 1
        assert frames < 20

    task.goto_page = lambda page: None
    task.screenshot = screenshot
    task.appear = lambda rule: rule is task.I_GUILD_CLOSE_RED or rule is task.I_GUILD_SHRINE
    monkeypatch.setattr('tasks.RichMan.guild.time.sleep', lambda _: None)
    task.execute_guild(SimpleNamespace(enable=True, mystery_amulet=True, black_daruma_scrap=False, skin_ticket=False))
    assert task.device.swipe.call_count == 8
