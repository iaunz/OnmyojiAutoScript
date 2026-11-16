"""Exercise fatigue priority through the normal task loop without a device."""
from types import SimpleNamespace

import pytest

from module.exception import TaskEnd
from tasks.MetaDemon.config import MetaDemon
from tasks.MetaDemon.script_task import ScriptTask


class ActionSelected(Exception):
    pass


@pytest.mark.parametrize('fatigue,enabled,own_boss,expected', [
    (60, True, False, 'shared'),
    (61, True, False, 'summon'),
    (90, True, False, 'summon'),
    (100, True, False, 'summon'),
    (101, True, False, 'exit'),
    (61, False, False, 'shared'),
    (61, True, True, 'own'),
])
def test_summoning_priority_boundaries(fatigue, enabled, own_boss, expected):
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(meta_demon=MetaDemon.model_validate({
        'meta_demon_config': {
            'meta_crafting_card': False,
            'md_fatigue_summon_first': enabled,
        },
        'switch_soul': {'enable': False, 'enable_switch_by_name': False},
    }))
    visible = {task.I_BATTLE_DEMON.name}
    visible.add(task.I_BOSS_CONVENE.name if own_boss else task.I_BOSS_EMPTY.name)
    task.appear = lambda rule, **kwargs: rule.name in visible
    task.screenshot = lambda: None
    task.enter = lambda *args: None
    task.ocr_appear = lambda rule: True
    task.current_exhaustion = lambda: fatigue
    task.is_star56 = lambda: False
    task.ui_click = lambda *args, **kwargs: True
    task.set_next_run = lambda **kwargs: None
    selected = []
    task.click = lambda rule, **kwargs: selected.append(
        'own' if rule is task.I_BOSS_EMPTY else 'shared')

    def summon():
        assert selected == []
        raise ActionSelected('summon')

    def battle(*args):
        raise ActionSelected(selected[-1])

    task.find_demon = summon
    task.battle_boss = battle
    if expected == 'exit':
        with pytest.raises(TaskEnd):
            task.run()
    else:
        with pytest.raises(ActionSelected, match=expected):
            task.run()


def test_existing_saved_configs_get_default_and_preserve_opt_out():
    old = MetaDemon.model_validate({'meta_demon_config': {'auto_shared_boss': False}})
    assert old.meta_demon_config.md_fatigue_summon_first is True
    assert old.meta_demon_config.auto_shared_boss is False
    saved = old.model_dump()
    saved['meta_demon_config']['md_fatigue_summon_first'] = False
    assert MetaDemon.model_validate(saved).meta_demon_config.md_fatigue_summon_first is False
