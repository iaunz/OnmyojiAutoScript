import pytest

from tasks.MemoryScrolls.script_task import ScriptTask


class ContributionReplay(ScriptTask):
    def __init__(self, *, empty=False, stuck=False, popup=False):
        self.empty = empty
        self.stuck = stuck
        self.popup = popup
        self.frames = 0
        self.clicks = []
        self.contributions = 0

    def screenshot(self):
        self.frames += 1
        assert self.frames <= 120, 'Contribution did not stop on a stuck screen'

    def appear(self, asset, **kwargs):
        return self.empty and asset in (self.I_MS_ZERO_S, self.I_MS_ZERO_M, self.I_MS_ZERO_L)

    def appear_then_click(self, asset, **kwargs):
        assert asset is self.I_MS_CONTRIBUTE
        self.contributions += 1
        self.empty = not self.stuck
        return True

    def wait_until_appear(self, asset, **kwargs):
        assert asset is self.I_MS_CONTRIBUTED
        return self.popup

    def click(self, asset, **kwargs):
        self.clicks.append(asset.name)
        return True

    def swipe(self, *args, **kwargs):
        pytest.fail('Contribution must use the maximum buttons on the new UI')


@pytest.fixture(autouse=True)
def skip_animation_delays(monkeypatch):
    monkeypatch.setattr('tasks.MemoryScrolls.script_task.sleep', lambda _: None)


def test_empty_inventory_does_not_contribute():
    task = ContributionReplay(empty=True)

    task.contribute_memoryscrolls()

    assert task.contributions == 0
    assert task.clicks == []


def test_contribution_selects_all_sizes_and_stops_when_empty():
    task = ContributionReplay()

    task.contribute_memoryscrolls()

    assert task.contributions == 1
    assert task.clicks == [
        task.C_MS_MAX_S.name, task.C_MS_MAX_S.name,
        task.C_MS_MAX_M.name, task.C_MS_MAX_M.name,
        task.C_MS_MAX_L.name, task.C_MS_MAX_L.name,
    ]


@pytest.mark.parametrize('popup', [False, True])
def test_stuck_inventory_and_reward_popup_are_bounded(popup):
    task = ContributionReplay(stuck=True, popup=popup)

    task.contribute_memoryscrolls()

    assert task.contributions == 10
    assert task.clicks.count(task.C_MS_CONTRIBUTED.name) == (100 if popup else 0)
