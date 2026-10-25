from datetime import datetime, time, timedelta
from threading import RLock
from types import SimpleNamespace

import pytest

from module.config.config import Config
from tasks.Dokan import script_task as dokan_module
from tasks.Dokan.script_task import ScriptTask


@pytest.mark.parametrize('server_hour', [9, 19])
def test_first_attack_retries_at_interval_without_server_rescheduling(monkeypatch, server_hour):
    now = datetime(2026, 10, 26, 19, 30)
    class Clock(datetime):
        @classmethod
        def now(cls):
            return now
    monkeypatch.setattr(dokan_module, 'datetime', Clock)
    scheduler = SimpleNamespace(
        failure_interval=timedelta(minutes=3), server_update=time(server_hour),
        float_time=time(0, 0, 30), delay_date=1, next_run=None,
    )
    config = object.__new__(Config)
    config.model = SimpleNamespace(dokan=SimpleNamespace(
        scheduler=scheduler,
        attack_count_config=SimpleNamespace(remain_attack_count=1, daily_attack_count=2),
    ))
    config.reload = lambda: None
    config.save = lambda: None
    config.lock_config = RLock()
    task = object.__new__(ScriptTask)
    task.config = config
    task.start_time = now
    # Keep the real set_next_run -> task_delay path to catch server-time override.
    task.next_run(is_dokan_activated=True)
    assert scheduler.next_run == now + timedelta(minutes=3)
