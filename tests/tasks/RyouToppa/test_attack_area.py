"""Replay raid selection with real click intervals and the device click guard."""

from collections import Counter, deque
from datetime import datetime
from types import SimpleNamespace

import pytest

from module.base import timer as timer_module
from module.device.device import Device
from module.exception import TaskEnd
from tasks.GameUi.page import page_kekkai_toppa, page_main
from tasks.RealmRaid.assets import RealmRaidAssets
from tasks.RyouToppa import script_task as raid_module
from tasks.RyouToppa.config import RyouToppa


class ReplayClock:
    def __init__(self):
        self.now = 100.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RaidReplay(raid_module.ScriptTask):
    def __init__(self, monkeypatch, *, enter_on=None, entry_delay=0,
                 open_on=1, close_on=1, battle_result=True):
        self.clock = ReplayClock()
        monkeypatch.setattr(timer_module, 'time', self.clock)
        monkeypatch.setattr(raid_module, 'time', self.clock)
        self.config = SimpleNamespace(ryou_toppa=RyouToppa())
        self.config.ryou_toppa.raid_config.limit_count = 1
        self.interval_timer = {}
        self.current_count = 0
        self.start_time = datetime.now()
        self.frames = 0
        self.selected = None
        self.popup_visible = False
        self.in_battle = False
        self.enter_at = None
        self.enter_on = enter_on or {}
        self.entry_delay = entry_delay
        self.open_on = open_on
        self.close_on = close_on
        self.battle_result = battle_result
        self.selections = Counter()
        self.challenges = Counter()
        self.safe_clicks = []
        self.last_challenge_at = None
        self.battles = []
        self.destinations = []
        self.schedules = []
        self.device = SimpleNamespace(
            click=self.device_click,
            click_record=deque(maxlen=15),
            click_record_clear=lambda: self.device.click_record.clear(),
            stuck_record_add=lambda name: None,
        )

    def screenshot(self):
        self.frames += 1
        assert self.frames < 500, 'Raid selection did not terminate'
        self.clock.sleep(0.25)
        if self.enter_at is not None and self.clock.time() >= self.enter_at:
            self.in_battle = True
            self.popup_visible = False
            self.enter_at = None

    def appear(self, asset, **kwargs):
        if asset is self.I_TOPPA_RECORD or asset is self.I_RYOU_REWARD:
            return not self.in_battle
        if asset is RealmRaidAssets.I_FIRE:
            return self.popup_visible
        return False

    def device_click(self, x, y, control_name):
        Device.click_record_add(self.device, control_name)
        Device.click_record_check(self.device)
        if control_name == RealmRaidAssets.I_FIRE.name:
            assert self.popup_visible
            self.challenges[self.selected] += 1
            self.last_challenge_at = self.clock.time()
            if self.challenges[self.selected] == self.enter_on.get(self.selected):
                self.enter_at = self.clock.time() + self.entry_delay
        elif control_name == self.C_SAFE_AREA.name:
            self.safe_clicks.append(self.clock.time())
            if len(self.safe_clicks) >= self.close_on:
                self.popup_visible = False
        else:
            for index, area in enumerate(raid_module.area_map):
                if control_name == area['rule_click'].name:
                    assert not self.popup_visible, 'Clicked a realm through the previous popup'
                    self.selected = index
                    self.selections[index] += 1
                    self.popup_visible = self.selections[index] >= self.open_on
                    break
            else:
                raise AssertionError(f'Unexpected click: {control_name}')

    def run_general_battle(self, config):
        assert self.in_battle
        self.battles.append(self.selected)
        self.current_count += 1
        self.in_battle = False
        return self.battle_result

    def goto_page(self, page):
        self.destinations.append(page)

    def ui_click(self, *args, **kwargs):
        return True

    def has_ticket(self):
        return True

    def set_next_run(self, **kwargs):
        self.schedules.append(kwargs)


@pytest.mark.parametrize('close_on', [1, 2])
def test_five_failed_challenges_close_popup_before_skipping(monkeypatch, close_on):
    task = RaidReplay(monkeypatch, close_on=close_on)

    assert task.attack_area(0) is False
    assert task.challenges == {0: 5}
    assert task.selections == {0: 1}
    assert len(task.safe_clicks) == close_on
    assert task.safe_clicks[0] - task.last_challenge_at >= 2
    assert task.popup_visible is False
    assert task.battles == []
    assert not task.device.click_record


@pytest.mark.parametrize('entry_delay', [0, 1.5])
@pytest.mark.parametrize('battle_result', [False, True])
def test_last_challenge_can_still_enter_battle(monkeypatch, entry_delay, battle_result):
    task = RaidReplay(monkeypatch, enter_on={0: 5}, entry_delay=entry_delay,
                      battle_result=battle_result)

    assert task.attack_area(0) is battle_result
    assert task.challenges == {0: 5}
    assert task.battles == [0]
    assert task.safe_clicks == []


def test_repeated_area_clicks_without_a_challenge_button_are_bounded(monkeypatch):
    task = RaidReplay(monkeypatch, open_on=100)

    assert task.attack_area(0) is False
    assert task.selections == {0: 5}
    assert not task.challenges
    assert task.battles == []


def test_last_selection_can_still_open_a_challenge(monkeypatch):
    task = RaidReplay(monkeypatch, open_on=5, enter_on={0: 1})

    assert task.attack_area(0) is True
    assert task.selections == {0: 5}
    assert task.challenges == {0: 1}
    assert task.battles == [0]


def test_skipped_realms_do_not_exhaust_the_next_realms_retries_or_click_guard(monkeypatch):
    task = RaidReplay(monkeypatch, enter_on={2: 1})

    assert task.attack_area(0) is False
    assert task.attack_area(1) is False
    assert task.attack_area(2) is True
    assert task.challenges == {0: 5, 1: 5, 2: 1}
    assert task.selections == {0: 1, 1: 1, 2: 1}
    assert task.battles == [2]


def test_run_moves_to_the_next_realm_after_challenge_retries(monkeypatch):
    task = RaidReplay(monkeypatch, enter_on={1: 1})

    with pytest.raises(TaskEnd):
        task.run()

    assert task.challenges == {0: 5, 1: 1}
    assert task.battles == [1]
    assert task.current_count == 1
    assert task.destinations == [page_kekkai_toppa, page_main]
    assert task.schedules == [dict(task='RyouToppa', finish=True, server=True, success=True)]
