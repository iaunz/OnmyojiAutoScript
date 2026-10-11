from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import script as script_module
from module.exception import GameOcrError, TaskEnd


@pytest.mark.parametrize('save_fails', [False, True])
@pytest.mark.parametrize('restart_enabled', [False, True])
def test_ocr_error_runs_restart_even_when_scheduled_restart_is_disabled(
        monkeypatch, save_fails, restart_enabled):
    script = object.__new__(script_module.Script)
    script.instance_guard = None
    script._try_acquire_queue_token = Mock(return_value=True)
    script.device = SimpleNamespace(screenshot=Mock())
    script.config = SimpleNamespace(
        model=SimpleNamespace(running_task='RealmRaid'),
        restart=SimpleNamespace(scheduler=SimpleNamespace(enable=restart_enabled)),
        task_call=Mock(side_effect=AssertionError('Recovery must not depend on scheduling')),
    )
    script.save_error_log = Mock(side_effect=OSError('Disk unavailable') if save_fails else None)
    commands = []

    def load_module(name, path):
        command = Path(path).parent.name

        class Task:
            def __init__(self, config, device):
                assert config.model.running_task == command

            def run(self):
                commands.append(command)
                if command == 'RealmRaid':
                    raise GameOcrError('Ticket OCR exhausted')
                assert command == 'Restart'
                raise TaskEnd

        return SimpleNamespace(ScriptTask=Task)

    monkeypatch.setattr(script_module, 'load_module', load_module)
    assert script.run('RealmRaid') is False
    assert commands == ['RealmRaid', 'Restart']
    assert script.config.model.running_task == 'RealmRaid'
    assert script.config.restart.scheduler.enable is restart_enabled
    script.save_error_log.assert_called_once_with()
