from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from tasks.KekkaiActivation import script_task


@pytest.mark.parametrize('yellow_score,gray_score,screened', [
    (0.96, 0.99, True),
    (0.99, 0.96, False),
])
def test_gray_activation_button_does_not_block_card_selection(
        monkeypatch, yellow_score, gray_score, screened):
    monkeypatch.setattr(script_task.time, 'sleep', lambda _: None)
    task = object.__new__(script_task.ScriptTask)
    task.I_A_ACTIVATE_YELLOW = deepcopy(task.I_A_ACTIVATE_YELLOW)
    task.I_A_ACTIVATE_GRAY = deepcopy(task.I_A_ACTIVATE_GRAY)
    task.goto_cards = lambda: None
    task.screenshot = lambda: None
    statuses, effects = iter([False, True]), iter([False, True])
    task.check_card_status = lambda: next(statuses)
    task.check_card_effect = lambda: next(effects)
    task.ocr_time = lambda: timedelta(minutes=5)
    task.set_next_run = lambda *args, **kwargs: None
    selections = []
    task.screening_card = selections.append

    def appear(rule, **kwargs):
        if rule is task.I_A_ACTIVATE_YELLOW:
            rule.last_score = yellow_score
            return yellow_score >= kwargs['threshold']
        if rule is task.I_A_ACTIVATE_GRAY:
            rule.last_score = gray_score
            return True
        return False

    task.appear = appear
    assert task.run_activation(SimpleNamespace(card_type='selected type')) is False
    assert selections == (['selected type'] if screened else [])
