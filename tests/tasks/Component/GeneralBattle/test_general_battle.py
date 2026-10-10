from types import SimpleNamespace

import numpy as np
import pytest

from module.config.config import Config
from module.config.config_model import ConfigModel
from tasks.ActivityShikigami.config import GeneralBattleConfig as ActivityBattleConfig
from tasks.Component.GeneralBattle import general_battle as battle_module
from tasks.Component.GeneralBattle.battle import Battle
from tasks.Component.GeneralBattle.config_general_battle import (
    GeneralBattleConfig, GreenMarkEnum, GreenMarkType,
)
from tasks.OtherWorldTwilight.config import OtherWorldTwilight, OWTBattleConfig


def test_general_battle_forwards_name_mark_configuration():
    config = OWTBattleConfig(green_enable=True, green_mark_name='缘结神')
    calls = []
    battle = SimpleNamespace(
        current_count=0,
        battle_before=lambda *args: None,
        is_in_battle=lambda screenshot: True,
        green_mark=lambda *args, **kwargs: calls.append((args, kwargs)),
        battle_wait=lambda **kwargs: True,
    )
    assert battle_module.GeneralBattle.run_general_battle(battle, config=config) is True
    assert calls == [((True, GreenMarkType.GREEN_LEFT1), {
        'green_mark_type': GreenMarkEnum.NAME, 'green_mark_name': '缘结神',
    })]


def test_new_battle_loadout_keeps_name_mark_configuration():
    battle = object.__new__(Battle)
    config = OWTBattleConfig(green_enable=True, green_mark_name='缘结神')
    _, options = battle.loadout_from_config(config)
    assert options['green'].green_mark_type == GreenMarkEnum.NAME
    assert options['green'].green_mark_name == '缘结神'


def test_green_mark_name_uses_ocr_box_and_roi_offsets():
    clicks = []
    battle = object.__new__(battle_module.GeneralBattle)
    battle.screenshot = lambda: None
    battle.device = SimpleNamespace(
        image=None, click=lambda *args, **kwargs: clicks.append((args, kwargs)),
    )
    battle.O_GREEN_MARK_AREA = SimpleNamespace(
        roi=(84, 256, 1116, 308),
        detect_and_ocr=lambda image: [SimpleNamespace(
            ocr_text='缘结神', box=np.array([[120, 30], [160, 30], [160, 50], [120, 50]]),
        )],
    )
    battle.green_mark_name('缘结神')
    assert clicks == [((209, 316), {'control_name': '缘结神'})]


def _real_config(task_name='OtherWorldTwilight'):
    config = object.__new__(Config)
    config.model = ConfigModel.model_construct(
        running_task=task_name,
        other_world_twilight=OtherWorldTwilight(
            general_battle_config=OWTBattleConfig(green_enable=True, green_mark_name='缘结神'),
        ),
    )
    return config


def test_navigation_battle_uses_real_task_config_and_existing_task_runner():
    config = _real_config()
    assert config.general_battle_config is None
    calls = []
    task = SimpleNamespace(config=config, device=object(), current_count=3)

    def run_general_battle(*, config):
        calls.append(config)
        task.current_count += 1
        return True

    task.run_general_battle = run_general_battle
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [config.other_world_twilight.general_battle_config]
    assert task.current_count == 4


def test_navigation_battle_uses_initialized_conf_before_scheduler_config():
    conf = OtherWorldTwilight()
    calls = []
    task = SimpleNamespace(
        config=_real_config(), conf=conf,
        run_general_battle=lambda **kwargs: calls.append(kwargs['config']) or True,
    )
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [conf.general_battle_config]


def test_navigation_battle_uses_session_category_without_scheduler_task():
    config = _real_config(task_name='')
    calls = []
    task = SimpleNamespace(
        config=config, navigator=SimpleNamespace(task_category='other_world_twilight'),
        run_general_battle=lambda **kwargs: calls.append(kwargs['config']) or True,
    )
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [config.other_world_twilight.general_battle_config]


@pytest.mark.parametrize('value', [None, ActivityBattleConfig(), {'green_enable': True}])
def test_navigation_battle_rejects_nonstandard_config(value):
    calls = []
    task = SimpleNamespace(
        config=SimpleNamespace(general_battle_config=value),
        conf=SimpleNamespace(general_battle_config=value),
        run_general_battle=lambda **kwargs: calls.append(kwargs['config']) or True,
    )
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [None]


def test_navigation_battle_preserves_direct_config_compatibility():
    config = GeneralBattleConfig(lock_team_enable=True)
    calls = []
    task = SimpleNamespace(
        config=SimpleNamespace(general_battle_config=config),
        run_general_battle=lambda **kwargs: calls.append(kwargs['config']) or True,
    )
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [config]


def test_navigation_battle_falls_back_for_tasks_without_battle_runner(monkeypatch):
    calls = []
    config, device = SimpleNamespace(general_battle_config=None), object()

    class DefaultBattle:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def run_general_battle(self, **kwargs):
            calls.append(kwargs)
            return False

    monkeypatch.setattr(battle_module, 'GeneralBattle', DefaultBattle)
    assert battle_module.run_task_or_default_general_battle(
        SimpleNamespace(config=config, device=device)
    ) is False
    assert calls == [{'config': config, 'device': device}, {'config': None}]


def test_navigation_battle_does_not_retry_exceptions_from_task_runner():
    calls = []

    def broken(**kwargs):
        calls.append(kwargs)
        raise AttributeError('battle failure')

    task = SimpleNamespace(config=SimpleNamespace(), run_general_battle=broken)
    with pytest.raises(AttributeError, match='battle failure'):
        battle_module.run_task_or_default_general_battle(task)
    assert len(calls) == 1


def test_default_navigation_battle_keeps_scheduler_identity(monkeypatch):
    config = _real_config()
    calls = []

    def run_battle(self, **kwargs):
        calls.append((self.get_task_name(), kwargs['config']))
        return True

    monkeypatch.setattr(battle_module.GeneralBattle, 'run_general_battle', run_battle)
    task = SimpleNamespace(
        config=config, device=object(), get_task_name=lambda: 'OtherWorldTwilight',
    )
    assert battle_module.run_task_or_default_general_battle(task) is True
    assert calls == [('OtherWorldTwilight', config.other_world_twilight.general_battle_config)]
