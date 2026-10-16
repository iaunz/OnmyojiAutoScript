from types import SimpleNamespace

import pytest

from tasks import base_task
from tasks.base_task import BaseTask


@pytest.mark.parametrize('running,expected', [
    ('WantedQuests', 'WantedQuests'), ('wanted_quests', 'WantedQuests'), ('', 'Orochi'),
])
def test_reused_task_implementation_keeps_the_scheduled_task_name(monkeypatch, running, expected):
    monkeypatch.setattr(base_task.inspect, 'getfile', lambda cls: 'tasks/Orochi/script_task.py')
    task = object.__new__(BaseTask)
    task.config = SimpleNamespace(model=SimpleNamespace(running_task=running))
    assert task.get_task_name() == expected
