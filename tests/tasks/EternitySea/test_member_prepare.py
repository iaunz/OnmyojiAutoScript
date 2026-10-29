from types import SimpleNamespace
import pytest
from tasks.EternitySea.script_task import ScriptTask, page_soul_zones


@pytest.mark.parametrize('locked', [True, False])
def test_member_prepares_selected_layer_and_lock_before_accepting_invites(locked):
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(model=SimpleNamespace(eternity_sea=SimpleNamespace(
        eternity_sea_config=SimpleNamespace(layer=4),
        general_battle_config=SimpleNamespace(lock_team_enable=locked))))
    calls = []
    task.goto_page = lambda page: calls.append(('page', page))
    task._enter_eternity_sea = lambda: calls.append('enter')
    task.check_layer = lambda layer: calls.append(('layer', layer))
    task.check_lock = lambda flag: calls.append(('lock', flag))
    class Prepared(Exception): pass
    def battle_record(name):
        assert calls == [('page', page_soul_zones), 'enter', ('layer', 4), ('lock', locked)]
        raise Prepared
    task.device = SimpleNamespace(stuck_record_add=battle_record)
    with pytest.raises(Prepared):
        task.run_member()
