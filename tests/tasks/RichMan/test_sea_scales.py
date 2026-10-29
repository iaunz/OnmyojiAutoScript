from types import SimpleNamespace
import pytest
from tasks.RichMan.mall import scales as module


@pytest.mark.parametrize('requested,remaining,money,expected', [
    (0, 30, 10000, []), (4, 30, 10000, [4]), (30, 8, 10000, [None]),
    (30, 30, 1000, [5]), (30, 30, 399, []), (30, 0, 10000, []),
])
def test_auto_sea_purchase_is_one_batch_with_config_stock_and_budget_limits(monkeypatch, requested, remaining, money, expected):
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    task = object.__new__(module.Scales)
    task.config = SimpleNamespace(rich_man=SimpleNamespace(scales=SimpleNamespace(enable_book_auto=True)))
    task.device = SimpleNamespace(image=None)
    task.screenshot = lambda: None
    task.appear = lambda asset: True
    task.O_SCA_NUMBER_SEA = SimpleNamespace(ocr=lambda image: remaining)
    task.O_SCA_RES_SEA = SimpleNamespace(ocr=lambda image: money)
    calls = []
    task._scales_buy_more = lambda asset, number=None: calls.append(number)
    task._scales_sea(requested)
    assert calls == expected
