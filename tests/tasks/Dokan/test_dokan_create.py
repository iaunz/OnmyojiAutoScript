from types import SimpleNamespace
import pytest
from module.exception import TaskEnd
from tasks.Dokan.script_task import ScriptTask, DokanScene


@pytest.mark.parametrize('already_inside,enabled,count,creates', [
    (True, True, 2, 1), (False, True, 2, 1),
    (True, False, 2, 0), (True, True, 0, 0),
])
def test_create_once_per_entry_and_not_each_search_loop(already_inside, enabled, count, creates):
    task = object.__new__(ScriptTask)
    task.config = SimpleNamespace(save=lambda: None, dokan=SimpleNamespace(
        dokan_config=SimpleNamespace(dokan_attack_priority=0, monday_to_thursday=False,
                                    try_start_dokan=enabled, find_dokan_score=2),
        attack_count_config=SimpleNamespace(init_attack_count=lambda **kwargs: None),
    ))
    events = []
    reads = 0
    def scene(*args):
        nonlocal reads
        reads += 1
        assert reads < 10
        return (already_inside or reads > 1, DokanScene.RYOU_DOKAN_SCENE_FINDING_DOKAN)
    task.get_current_scene = scene
    task.goto_dokan_scene = lambda: events.append('enter')
    task.update_remain_attack_count = lambda: count
    task.creat_dokan = lambda: events.append('create')
    results = iter([True, False])
    task.find_dokan = lambda score: next(results)
    task.screenshot = lambda: None
    task.wait_until_appear = lambda *args: None
    task.goto_main = lambda: None
    task.next_run = lambda **kwargs: None
    with pytest.raises(TaskEnd):
        task.run()
    assert events.count('create') == creates
    assert events.count('enter') == int(not already_inside)
