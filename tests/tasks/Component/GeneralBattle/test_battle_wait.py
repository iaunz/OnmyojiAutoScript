from contextvars import copy_context
from types import SimpleNamespace

import pytest

from tasks.Component.GeneralBattle.battle_wait import (
    BattleResult,
    BattleWait,
    BattleWaitPlan,
    HookSignal,
    OptionCompletionDefault,
    OptionPrepareDefault,
    OptionSetupDefault,
    OptionSuccessDefault,
    PerBattlePrepare,
    PerBattleState,
    PerTaskPreset,
    PerTaskState,
    battle_wait_options,
    battle_wait_strategy,
    runtime,
    _OPTION_CLASSES,
)


@pytest.fixture(autouse=True)
def reset_battle_wait_plan(monkeypatch):
    monkeypatch.setattr(battle_wait_options, 'options', {
        event: cls() for event, cls in _OPTION_CLASSES.items()
    })
    monkeypatch.setattr(runtime, 'task_owner', None)
    monkeypatch.setattr(runtime, 'pub_ctx', None)
    monkeypatch.setattr(runtime, 'pri_ctx', {})
    contexts = (
        battle_wait_strategy._context,
        battle_wait_options._context,
        battle_wait_options._decorator_options,
    )
    tokens = [context.set(None) for context in contexts]
    yield
    for context, token in zip(contexts, tokens):
        context.reset(token)


def capture(owner, *, battle_wait_plan, options):
    return battle_wait_plan, options


def test_default_plan_contains_default_hooks_and_sequence():
    plan = BattleWaitPlan()
    assert all(getattr(plan, hook) == 'default' for hook in plan.HOOKS_DEFAULT)
    assert plan.sequence == (
        'completion>interrupt>prepare>preset>green>red>echo>success>failure>idle'
    )
    assert plan.function_setup_name == '_bw_setup_default'


def test_decorator_passes_its_plan_to_the_wrapped_function():
    strategy = battle_wait_strategy('reserve_default', 'idle_default', failure='custom')
    plan, _ = strategy(capture)(object())
    assert plan.reserve == 'default'
    assert plan.idle == 'default'
    assert plan.failure == 'custom'


def test_with_context_uses_a_temporary_plan_and_restores_the_default_plan():
    strategy = battle_wait_strategy('success_default')
    wait = strategy(capture)
    with battle_wait_strategy('success_default', failure='custom'):
        assert wait(object())[0].failure == 'custom'
    assert battle_wait_strategy._context.get() is None
    assert wait(object())[0] is strategy.battle_wait_plan


@pytest.mark.parametrize('strategies', [('default', 'activity'), ('activity', 'default')])
@pytest.mark.parametrize('random_click', [False, True])
def test_task_strategies_are_independent_of_decoration_order(strategies, random_click):
    tasks = {name: battle_wait_strategy(success=name)(capture) for name in strategies}
    for name, wait in tasks.items():
        plan, _ = wait(object(), random_click_swipt_enable=random_click)
        assert plan.success == name
        assert hasattr(plan, 'randomclick') is random_click
    for name, wait in tasks.items():
        assert wait(object())[0].success == name


def test_event_and_strategy_can_be_configured_with_both_supported_forms():
    plan = BattleWaitPlan('yyy_default', abcd='edf')
    assert plan.yyy == 'default'
    assert plan.abcd == 'edf'
    assert plan.sequence_function_names()[-3:-1] == ['_bw_yyy_default', '_bw_abcd_edf']


def test_an_event_cannot_be_configured_with_two_strategies():
    with pytest.raises(ValueError, match='configured more than once'):
        BattleWaitPlan('success_default', success='custom')


def test_custom_sequence_controls_hook_order():
    sequence = 'failure>yyy>completion>interrupt>prepare>preset>green>red>echo>success>idle'
    plan = BattleWaitPlan('yyy_default', sequence=sequence)
    assert plan.sequence_function_names() == [f'_bw_{event}_default' for event in sequence.split('>')]


def test_custom_events_without_sequence_are_inserted_before_idle_in_argument_order():
    plan = BattleWaitPlan('yyy_default', 'abcd_edf')
    assert plan.sequence.endswith('failure>yyy>abcd>idle')


def test_dynamic_override_is_only_valid_for_the_current_call():
    strategy = battle_wait_strategy('success_default')
    wait = strategy(capture)
    overridden, options = wait(object(), random_click_swipt_enable=True)
    assert overridden is not strategy.battle_wait_plan
    assert overridden.randomclick == 'default'
    assert 'randomclick' in options
    assert not hasattr(strategy.battle_wait_plan, 'randomclick')
    assert wait(object(), random_click_swipt_enable=False)[0] is strategy.battle_wait_plan


def test_nested_context_restores_each_task_strategy_even_after_an_exception():
    ordinary = battle_wait_strategy()(capture)
    activity = battle_wait_strategy(success='activity')(capture)
    outer = battle_wait_strategy(success='outer')
    inner = battle_wait_strategy(success='inner')
    assert ordinary(object())[0].success == 'default'
    assert activity(object())[0].success == 'activity'
    with outer:
        assert activity(object())[0].success == 'outer'
        with pytest.raises(RuntimeError, match='interrupted'):
            with inner:
                assert ordinary(object())[0].success == 'inner'
                raise RuntimeError('interrupted')
        assert activity(object())[0].success == 'outer'
    assert ordinary(object())[0].success == 'default'
    assert activity(object())[0].success == 'activity'


def test_same_context_manager_can_be_nested_and_used_in_independent_contexts():
    strategy = battle_wait_strategy(success='activity')
    options = battle_wait_options(prepare={'lock_team': True})
    wait = battle_wait_strategy()(capture)
    first, second = copy_context(), copy_context()
    first.run(strategy.__enter__)
    second.run(strategy.__enter__)
    first.run(options.__enter__)
    second.run(options.__enter__)
    first.run(options.__exit__, None, None, None)
    first.run(strategy.__exit__, None, None, None)
    assert first.run(wait, object())[0].success == 'default'
    assert second.run(wait, object())[0].success == 'activity'
    assert second.run(wait, object())[1]['prepare'].lock_team is True
    second.run(options.__exit__, None, None, None)
    second.run(strategy.__exit__, None, None, None)
    with strategy, options:
        with strategy, options:
            assert wait(object())[0].success == 'activity'
        assert wait(object())[1]['prepare'].lock_team is True
    assert wait(object())[0].success == 'default'
    assert wait(object())[1]['prepare'].lock_team is False


def test_options_decorator_and_with_are_scoped_to_the_current_call():
    wait = battle_wait_options(
        success={'excludes_1': ['C_REWARD_1']}, prepare={'lock_team': True}
    )(battle_wait_strategy()(capture))
    assert wait(object())[1]['success'].excludes_1 == ['C_REWARD_1']
    with battle_wait_options(success={'excludes_1': ['C_END_MESSAGE_RIGHT_TOP']}):
        options = wait(object())[1]
        assert options['success'].excludes_1 == ['C_END_MESSAGE_RIGHT_TOP']
        assert options['prepare'].lock_team is True
        with pytest.raises(RuntimeError):
            with battle_wait_options(prepare={'lock_team': False}):
                assert wait(object())[1]['prepare'].lock_team is False
                raise RuntimeError('interrupted')
        assert wait(object())[1]['prepare'].lock_team is True
    assert wait(object())[1]['success'].excludes_1 == ['C_REWARD_1']
    assert battle_wait_options._context.get() is None
    assert battle_wait_options._decorator_options.get() is None


def test_cross_task_options_do_not_leak_between_tasks_or_calls():
    ordinary = battle_wait_options(success={'excludes_1': ['C_REWARD_1']})(
        battle_wait_strategy()(capture)
    )
    activity = battle_wait_options(success={'excludes_1': ['C_END_ACTIVITY_REWARD']})(
        battle_wait_strategy(success='activity')(capture)
    )
    assert ordinary(object())[0].success == 'default'
    assert activity(object())[0].success == 'activity'
    ordinary(object())[1]['success'].excludes_1.clear()
    assert ordinary(object())[1]['success'].excludes_1 == ['C_REWARD_1']
    assert activity(object())[1]['success'].excludes_1 == ['C_END_ACTIVITY_REWARD']
    assert battle_wait_strategy()(capture)(object())[1]['success'] == OptionSuccessDefault()


def test_options_decorator_restores_context_after_exception():
    @battle_wait_options(prepare={'lock_team': True})
    def fail(owner):
        assert battle_wait_options.current()['prepare'].lock_team is True
        raise RuntimeError('interrupted')

    with battle_wait_options(success={'excludes_1': ['C_REWARD_1']}):
        with pytest.raises(RuntimeError):
            fail(object())
        options = battle_wait_options.current()
        assert options['prepare'].lock_team is False
        assert options['success'].excludes_1 == ['C_REWARD_1']


class ReplayBattle(BattleWait):
    def __init__(self):
        self.events = []
        self.frames = 0

    def screenshot(self):
        self.frames += 1
        assert self.frames < 5, 'battle did not complete'
        self.events.append('screenshot')

    def _bw_setup_record(self, pub, pri):
        self.events.append('setup')
        return HookSignal.DONE

    def _bw_prepare_default(self, pub, pri):
        return HookSignal.CONTINUE

    def _bw_success_record(self, pub, pri):
        self.events.append('success')
        pub.per_battle.success = BattleResult.SUCCESS
        return runtime.hook_enabled_update(enable=('completion',), disable=('success', 'failure'))

    def _bw_completion_record(self, pub, pri):
        self.events.append('completion')
        return HookSignal.DONE

    @battle_wait_strategy(setup='record', success='record', completion='record')
    def battle_wait(self, *args, **kwargs):
        return self.battle_wait_with_strategy(*args, **kwargs)


def test_setup_runs_before_the_wait_loop_and_completion_waits_for_settlement():
    battle = ReplayBattle()
    assert battle.battle_wait() is True
    assert battle.events == ['setup', 'screenshot', 'success', 'screenshot', 'completion']


def test_custom_hook_is_resolved_and_executed_in_the_configured_sequence():
    class CustomBattle(ReplayBattle):
        def _bw_yyy_multi_word(self, pub, pri):
            self.events.append('yyy')
            pub.per_battle.success = BattleResult.SUCCESS
            return runtime.hook_enabled_update(enable=('completion',), disable=())

    battle = CustomBattle()
    with battle_wait_strategy(
        setup='record', success='record', completion='record', yyy='multi_word',
        sequence='yyy>completion>interrupt>prepare>preset>green>red>echo>success>failure>idle',
    ):
        assert battle.battle_wait() is True
    assert battle.events == ['setup', 'screenshot', 'yyy', 'completion']


def test_activity_reward_is_collected_after_another_task_is_decorated(monkeypatch):
    ordinary = battle_wait_strategy()(capture)

    class ActivityBattle(BattleWait):
        def __init__(self):
            self.reward_visible = True
            self.frames = 0
            self.clicks = []
            self.device = SimpleNamespace(
                stuck_record_add=lambda name: None,
                click_record_clear=lambda: None,
            )

        def screenshot(self):
            self.frames += 1
            assert self.frames < 10, 'Activity reward was not collected'

        def is_in_real_battle(self, is_screenshot=False):
            return False

        def appear(self, asset, **kwargs):
            return asset is self.I_UI_REWARD and self.reward_visible

        def appear_then_click(self, asset, **kwargs):
            return False

        def click(self, asset, **kwargs):
            self.clicks.append(asset.name)
            self.reward_visible = False

        @battle_wait_strategy(success='activity')
        def battle_wait(self, *args, **kwargs):
            return self.battle_wait_with_strategy(*args, **kwargs)

    monkeypatch.setattr('tasks.Component.GeneralBattle.battle_wait.random.random', lambda: 1)
    task = ActivityBattle()
    assert task.battle_wait(random_click_swipt_enable=False) is True
    assert task.clicks == ['exclude_click_activity']
    assert runtime.pub_ctx.per_task.count == 1
    assert ordinary(object())[0].success == 'default'


def _make_runtime_probe():
    class RuntimeProbe(BattleWait):
        def __init__(self):
            self.calls = []

        def _bw_setup_probe(self, pub, pri):
            self.calls.append(('setup', pub, pri))
            return HookSignal.DONE

        def _bw_completion_probe(self, pub, pri):
            self.calls.append(('completion', pub, pri))
            return HookSignal.DONE

        def _bw_success_probe(self, pub, pri):
            self.calls.append(('success', pub, pri))
            return HookSignal.DONE

    return RuntimeProbe()


def test_runtime_injects_shared_pub_and_per_hook_pri():
    battle = _make_runtime_probe()
    battle._bw_setup_probe()
    battle._bw_completion_probe()
    _, setup_pub, setup_pri = battle.calls[0]
    _, completion_pub, completion_pri = battle.calls[1]
    assert setup_pub is completion_pub is runtime.pub_ctx
    assert setup_pri is runtime.pri_ctx['_bw_setup_probe']
    assert completion_pri is runtime.pri_ctx['_bw_completion_probe']
    assert setup_pri is not completion_pri
    assert battle._bw_completion_probe.__name__ == '_bw_completion_probe'


def test_runtime_task_owner_switch_resets_per_task():
    battle = _make_runtime_probe()
    battle._bw_setup_probe()
    runtime.pub_ctx.cross['keep'] = 1
    runtime.pub_ctx.per_task.count = 4
    runtime._ensure_pri_default('_bw_preset_default')
    runtime.pri_ctx['_bw_preset_default'].per_task.done = True
    _make_runtime_probe()._bw_setup_probe()
    assert runtime.pub_ctx.cross == {'keep': 1}
    assert runtime.pub_ctx.per_task == PerTaskState()
    assert runtime.pri_ctx['_bw_preset_default'].per_task == PerTaskPreset()


def test_runtime_reset_per_battle_keeps_cross_and_per_task():
    battle = _make_runtime_probe()
    battle._bw_setup_probe()
    runtime.pub_ctx.cross['c'] = 1
    runtime.pub_ctx.per_task.count = 2
    runtime.pub_ctx.per_battle.success = BattleResult.SUCCESS
    runtime._ensure_pri_default('_bw_prepare_default')
    runtime.pri_ctx['_bw_prepare_default'].per_battle.done = True
    runtime.reset_per_battle()
    assert runtime.pub_ctx.cross == {'c': 1}
    assert runtime.pub_ctx.per_task.count == 2
    assert runtime.pub_ctx.per_battle == PerBattleState()
    assert runtime.pri_ctx['_bw_prepare_default'].per_battle == PerBattlePrepare()


def test_runtime_update_options_distributes_by_hook_event_name_and_resets_defaults():
    plan = BattleWaitPlan(setup='probe', completion='probe', success='multi_word')
    options = {
        'setup': OptionSetupDefault(excludes=['C_REWARD_1']),
        'completion': OptionCompletionDefault(excludes=['C_REWARD_2']),
        'success': OptionSuccessDefault(excludes_1=['C_REWARD_3']),
    }
    runtime.update_options(options, plan=plan)
    assert runtime.pub_ctx.options == options
    for hook in ('_bw_setup_probe', '_bw_completion_probe', '_bw_success_multi_word'):
        assert runtime.pri_ctx[hook].options is options[runtime.hook2event(hook)]
    runtime.update_options({}, plan=plan)
    assert runtime.pri_ctx['_bw_setup_probe'].options == OptionSetupDefault()
    assert runtime.pri_ctx['_bw_success_multi_word'].options == OptionSuccessDefault()


def test_runtime_str_shows_hook_name_and_state_fields():
    battle = _make_runtime_probe()
    battle._bw_setup_probe()
    text = str(battle.__class__._bw_setup_probe)
    assert '_bw_setup_probe' in text
    assert 'count' in text
    assert 'hook_enabled' in text


@pytest.mark.parametrize('locked', [False, True])
def test_prepare_dismisses_soul_mismatch_dialog_before_progressing(locked):
    class PrepareBattle(BattleWait):
        def __init__(self):
            self.visible = [self.I_DISABLE_7DAYS_DIFF_SOUL, self.I_CONFIRM_CLOSE_DIFF_SOUL]
            self.clicked = []

        def appear_then_click(self, target, **kwargs):
            if self.visible and target is self.visible[0]:
                self.clicked.append(target)
                self.visible.pop(0)
                return True
            return False

        def is_in_real_battle(self, is_screenshot=False):
            return True

    battle = PrepareBattle()
    runtime.update_options({'prepare': OptionPrepareDefault(lock_team=locked)}, BattleWaitPlan())
    for _ in range(2):
        assert battle._bw_prepare_default() == HookSignal.CONTINUE
        assert runtime.pri_ctx['_bw_prepare_default'].per_battle.done is False
    assert battle.clicked == [battle.I_DISABLE_7DAYS_DIFF_SOUL, battle.I_CONFIRM_CLOSE_DIFF_SOUL]
    battle._bw_prepare_default()
    assert runtime.pri_ctx['_bw_prepare_default'].per_battle.done is True
