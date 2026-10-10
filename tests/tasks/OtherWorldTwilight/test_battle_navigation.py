from datetime import datetime

import pytest

from tasks.OtherWorldTwilight import script_task as owt_module
from tasks.OtherWorldTwilight.config import OtherWorldTwilight
from tasks.GameUi.page import page_battle, page_battle_prepare, page_battle_result, page_reward
from tasks.OtherWorldTwilight.page import page_owt


class SoloReplay(owt_module.ScriptTask):
    def __init__(self, page):
        self.conf = OtherWorldTwilight()
        self.conf.other_world_twilight_config.limit_count = 1
        self.current_count = 0
        self.start_time = datetime.now()
        self.page = page
        self.frames = 0
        self.destinations = []
        self.battles = []

    def goto_page(self, page):
        self.destinations.append(page)
        if len(self.destinations) > 1:
            self.current_count = 1

    def check_lock(self, *args):
        pass

    def screenshot(self):
        self.frames += 1
        assert self.frames < 5, 'unrecognized page never triggered recovery'

    def get_current_page(self, *args):
        return self.page

    def run_general_battle(self, config):
        self.battles.append(config)
        self.current_count += 1
        return True


@pytest.mark.parametrize('page', [page_battle_prepare, page_battle, page_reward, page_battle_result])
def test_solo_takes_over_all_battle_pages_and_counts_settlement(page):
    task = SoloReplay(page.clone())
    task.run_alone()
    assert task.battles == [task.conf.general_battle_config]
    assert task.current_count == 1
    assert task.destinations == [page_owt]


def test_solo_recovers_when_no_page_can_be_recognized(monkeypatch):
    class ExpiredAfterStart:
        active = False

        def __init__(self, limit):
            assert limit == 10

        def started(self):
            return self.active

        def start(self):
            self.active = True

        def reached(self):
            return self.active

        def clear(self):
            self.active = False

    monkeypatch.setattr(owt_module, 'Timer', ExpiredAfterStart)
    monkeypatch.setattr(owt_module, 'sleep', lambda seconds: None)
    task = SoloReplay(None)
    task.run_alone()
    assert task.destinations == [page_owt, page_owt]
    assert task.battles == []
