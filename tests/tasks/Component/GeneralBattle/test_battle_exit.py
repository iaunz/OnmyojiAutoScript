import pytest

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle


class BattleExitReplay(GeneralBattle):
    def __init__(self, *, screen='battle', background_exit_visible=True,
                 ignored_confirms=0):
        self.screen = screen
        self.background_exit_visible = background_exit_visible
        self.ignored_confirms = ignored_confirms
        self.frames = 0
        self.clicks = []

    def screenshot(self):
        self.frames += 1
        assert self.frames < 15, 'Kept clicking behind the exit confirmation dialog'

    def appear(self, asset, **kwargs):
        if asset is self.I_EXIT:
            return self.screen == 'battle' or (
                self.screen == 'confirm' and self.background_exit_visible
            )
        if asset is self.I_EXIT_ENSURE:
            return self.screen == 'confirm'
        if asset is self.I_FALSE:
            return self.screen == 'defeat'
        return False

    def appear_then_click(self, asset, **kwargs):
        if not self.appear(asset):
            return False
        self.clicks.append(asset.name)
        if asset is self.I_EXIT:
            self.screen = 'confirm'
        elif asset is self.I_EXIT_ENSURE:
            if self.ignored_confirms:
                self.ignored_confirms -= 1
            else:
                self.screen = 'defeat'
        elif asset is self.I_FALSE:
            self.screen = 'finished'
        return True

    def wait_until_appear(self, asset, **kwargs):
        assert self.appear(asset)
        return True

    def run_exit(self, method):
        if method == 'run_general_battle_back':
            return self.run_general_battle_back(
                GeneralBattleConfig(lock_team_enable=True), exit_four=True,
            )
        return self.exit_battle()


@pytest.mark.parametrize('method', ['run_general_battle_back', 'exit_battle'])
@pytest.mark.parametrize('background_exit_visible', [True, False])
def test_exit_confirms_dialog_before_clicking_the_background(method, background_exit_visible):
    task = BattleExitReplay(background_exit_visible=background_exit_visible)

    assert task.run_exit(method) is True
    assert task.screen == 'finished'
    assert task.clicks == [task.I_EXIT.name, task.I_EXIT_ENSURE.name, task.I_FALSE.name]


@pytest.mark.parametrize('method', ['run_general_battle_back', 'exit_battle'])
def test_already_open_exit_dialog_is_confirmed_without_reopening_it(method):
    task = BattleExitReplay(screen='confirm')

    assert task.run_exit(method) is True
    assert task.screen == 'finished'
    assert task.clicks == [task.I_EXIT_ENSURE.name, task.I_FALSE.name]


def test_exit_battle_ignores_confirmation_without_a_battle_anchor():
    task = BattleExitReplay(screen='confirm', background_exit_visible=False)

    assert task.exit_battle() is False
    assert task.clicks == []


@pytest.mark.parametrize('method', ['run_general_battle_back', 'exit_battle'])
def test_ignored_confirmation_click_retries_the_dialog_not_the_background(method):
    task = BattleExitReplay(ignored_confirms=1)

    assert task.run_exit(method) is True
    assert task.screen == 'finished'
    assert task.clicks == [
        task.I_EXIT.name, task.I_EXIT_ENSURE.name, task.I_EXIT_ENSURE.name, task.I_FALSE.name,
    ]


def test_exit_battle_does_nothing_outside_battle():
    task = BattleExitReplay(screen='finished')

    assert task.exit_battle() is False
    assert task.clicks == []
