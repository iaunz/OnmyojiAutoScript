import pytest

from tasks.WantedQuests import script_task as wanted


@pytest.mark.parametrize('selected', [False, True])
def test_invite_uses_the_wanted_quest_selection_marker(monkeypatch, selected):
    monkeypatch.setattr(wanted, 'sleep', lambda duration: None)
    task = object.__new__(wanted.ScriptTask)
    add_button = object()
    checked, confirmed = [], []

    def appear(asset, **kwargs):
        checked.append(asset)
        return asset is add_button or (asset is task.I_WQ_INVITE_SELECTED and selected)

    task.appear = appear
    task.screenshot = lambda: None
    task.ui_click = lambda *args, **kwargs: None
    task.click = lambda *args, **kwargs: True
    task.ui_click_until_disappear = lambda asset: confirmed.append(asset)
    task.invite_random(add_button)
    assert task.I_WQ_INVITE_SELECTED in checked
    assert bool(confirmed) is selected
