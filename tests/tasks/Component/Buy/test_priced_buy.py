from types import SimpleNamespace

import pytest

from tasks.Component.Buy import buy as buy_module
from tasks.Component.Buy.buy import Buy
from tasks.RichMan.mall.friendship_points import FriendshipPoints


def priced_task(price):
    task = object.__new__(Buy)
    task.calls = []
    task._buy_read_price = lambda: price
    task._buy_cancel = lambda check: task.calls.append('cancel')
    task.buy_one = lambda *args: task.calls.append('one') or True
    task.buy_more = lambda start, number: task.calls.append(('more', number)) or True
    task._buy_more_default = lambda start: task.calls.append('default') or True
    return task


@pytest.mark.parametrize('price,money,remain,more,expected', [
    (None, 500, 5, True, 'cancel'), (90, 500, 5, True, 'cancel'),
    (85, 85, 5, True, 'default'), (50, 100, 5, True, 'default'),
    (50, 250, 5, True, ('more', None)), (50, 49, 5, True, 'cancel'),
    (50, 49, 1, False, 'cancel'), (50, 50, 0, False, 'cancel'),
    (50, 50, 1, False, 'one'),
])
def test_price_and_affordability_guard_both_dialogs(price, money, remain, more, expected):
    task = priced_task(price)
    assert task._buy_with_price(None, None, more, 85, money, remain) is (expected != 'cancel')
    assert task.calls == [expected]


@pytest.mark.parametrize('balance,priced,expected', [(60, True, True), (60, False, False), (0, True, False)])
def test_discounted_ticket_uses_actual_price_not_max_price_as_balance_gate(balance, priced, expected):
    task = object.__new__(FriendshipPoints)
    task.device = SimpleNamespace(image=None)
    task.screenshot = lambda: None
    task.appear = lambda asset: True
    task._special_check_remain = lambda asset: 5
    task.buy_one_or_more = lambda *args, **kwargs: kwargs['money'] == balance
    task.buy_one = lambda *args: pytest.fail('Unexpected single purchase')
    assert task.buy_mall_one(SimpleNamespace(name='ticket'), None,
                             SimpleNamespace(ocr=lambda image: balance), 85,
                             max_price=85 if priced else None) is expected


@pytest.mark.parametrize('current', [0, 2])
def test_unverified_default_quantity_cancels_instead_of_incrementing(monkeypatch, current):
    monkeypatch.setattr(buy_module, 'Timer', lambda *args: SimpleNamespace(
        start=lambda: SimpleNamespace(reached=lambda: True)))
    task = object.__new__(Buy)
    task.device = SimpleNamespace(image=None)
    task.O_BUY_NUMBER = SimpleNamespace(ocr=lambda image: current)
    calls = []
    task._buy_cancel = lambda check: calls.append('cancel') or True
    task.buy_more = lambda *args: pytest.fail('Increment fallback can exceed budget')
    assert task._buy_more_default(None) is False
    assert calls == ['cancel']


@pytest.mark.parametrize('price,expected', [(0, None), (9, None), ('bad', None), (50, 50), (85, 85), (90, 90)])
def test_price_ocr_rejects_partial_digits_and_excludes_jade_icon(price, expected):
    task = object.__new__(Buy)
    task.device = SimpleNamespace(image=None)
    task.appear = lambda asset: True
    task.I_BUY_JADE = SimpleNamespace(roi_front=(600, 530, 42, 52))
    task.O_BUY_PRICE = SimpleNamespace(roi=None, ocr=lambda image: price)
    assert task._buy_read_price() == expected
    assert task.O_BUY_PRICE.roi == [642, 530, 60, 52]


@pytest.mark.parametrize('multiple', [True, False])
def test_dialog_detection_routes_to_price_check(multiple):
    task = object.__new__(Buy)
    task.screenshot = lambda: None
    check = object()
    task.appear = lambda asset: (asset is task.I_BUY_PLUS and multiple) or asset is check
    task._buy_with_price = lambda start, image, more, price, money, remain: more == multiple
    assert task.buy_one_or_more(None, check, max_price=85, money=100, remain=5)
