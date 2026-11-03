from types import SimpleNamespace

import numpy as np
import pytest

from module.exception import TaskEnd
from tasks.GameUi.page import page_daily
from tasks.TalismanPass.script_task import ScriptTask


@pytest.mark.parametrize('tab_visible', [False, True])
def test_task_tab_is_matched_before_claiming(tab_visible):
    task = object.__new__(ScriptTask)
    events = []
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    if tab_visible:
        rule = task.I_TASK_TAB
        x, y = rule.roi_front[:2]
        h, w = rule.image.shape[:2]
        screen[y:y+h, x:x+w] = rule.image
    task.device = SimpleNamespace(
        image=screen, click=lambda x, y, control_name: events.append('tab'),
    )
    task.interval_timer = {}
    task.config = SimpleNamespace(talisman_pass=SimpleNamespace(
        talisman=SimpleNamespace(level_reward=2, harvest_soul=False)))
    task.goto_page = lambda page: events.append('daily') if page == page_daily else None

    def in_task():
        # Clicking the visible tab opens the task panel; an absent tab is not clicked.
        events.append('check')
        return tab_visible

    task.in_task = in_task
    task.get_all = lambda: events.append('claim')
    task.get_flower = lambda level: events.append('flower')
    task.set_next_run = lambda **kwargs: events.append('scheduled')
    with pytest.raises(TaskEnd):
        task.run()
    assert events == (['daily', 'tab', 'check', 'claim', 'flower', 'scheduled']
                      if tab_visible else ['daily', 'check', 'flower', 'scheduled'])
