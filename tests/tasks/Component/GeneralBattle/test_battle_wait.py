import pytest

from tasks.Component.GeneralBattle.battle_wait import (
    BattleWait,
    BattleWaitPlan,
    HookSignal,
    battle_wait_strategy,
)


@pytest.fixture(autouse=True)
def reset_battle_wait_plan(monkeypatch):
    monkeypatch.setattr(battle_wait_strategy, 'options', None)
    token = battle_wait_strategy._context.set(None)
    yield
    battle_wait_strategy._context.reset(token)


def test_default_plan_contains_default_hooks_and_sequence():
    plan = BattleWaitPlan()

    assert tuple(getattr(plan, hook) for hook in BattleWaitPlan.HOOKS_DEFAULT) == (
        'default',
        'default',
        'default',
        'default',
        'default',
        'default',
    )
    assert plan.sequence == 'completion>interrupt>success>failure>idle'
    assert plan.function_setup_name == '_bw_setup_default'


def test_decorator_passes_its_plan_to_the_wrapped_function():
    strategy = battle_wait_strategy('reserve_default', 'idle_default', failure='custom')

    @strategy
    def battle_wait(owner, *, battle_wait_plan):
        return battle_wait_plan

    plan = battle_wait(object())

    assert plan.reserve == 'default'
    assert plan.idle == 'default'
    assert plan.failure == 'custom'


def test_with_context_uses_a_temporary_plan_and_restores_the_default_plan():
    strategy = battle_wait_strategy('success_default')

    @strategy
    def battle_wait(owner, *, battle_wait_plan):
        return battle_wait_plan

    default_plan = strategy.battle_wait_plan

    with battle_wait_strategy('success_default', failure='custom'):
        temporary_plan = battle_wait(object())
        assert temporary_plan.failure == 'custom'

    assert battle_wait_strategy._context.get() is None
    assert battle_wait(object()) is default_plan


def test_event_and_strategy_can_be_configured_with_both_supported_forms():
    plan = BattleWaitPlan('yyy_default', abcd='edf')

    assert plan.yyy == 'default'
    assert plan.abcd == 'edf'
    assert plan.sequence_function_names()[4:6] == [
        '_bw_yyy_default',
        '_bw_abcd_edf',
    ]


@pytest.mark.parametrize('strategies', [('default', 'activity'), ('activity', 'default')])
@pytest.mark.parametrize('random_click', [False, True])
def test_task_strategies_are_independent_of_decoration_order(strategies, random_click):
    def wait(owner, *, battle_wait_plan):
        return battle_wait_plan

    tasks = {
        name: battle_wait_strategy(success=name)(wait)
        for name in strategies
    }

    for name, wait in tasks.items():
        plan = wait(object(), random_click_swipt_enable=random_click)
        assert plan.success == name
        assert hasattr(plan, 'randomclick') is random_click

    # A later call must still use the task's own strategy.
    for name, wait in tasks.items():
        assert wait(object()).success == name


def test_activity_reward_is_collected_after_another_task_is_decorated(monkeypatch):
    from types import SimpleNamespace

    @battle_wait_strategy()
    def ordinary_wait(owner, *, battle_wait_plan):
        return battle_wait_plan

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

    # Keep the replay on the normal dismissal path, without random item inspection.
    monkeypatch.setattr('tasks.Component.GeneralBattle.battle_wait.random.random', lambda: 1)
    task = ActivityBattle()

    assert task.battle_wait(random_click_swipt_enable=False) is True
    assert task.clicks == ['exclude_click_activity']
    assert ordinary_wait(object()).success == 'default'


def test_an_event_cannot_be_configured_with_two_strategies():
    with pytest.raises(ValueError, match="configured more than once"):
        BattleWaitPlan('success_default', success='custom')


def test_setup_runs_before_the_wait_loop():
    class OrderedBattleWait(BattleWait):
        def __init__(self):
            self.events = []

        def screenshot(self):
            self.events.append('screenshot')

        def _bw_setup_record(self, bw_ctx):
            self.events.append('setup')
            return HookSignal.DONE

        def _bw_completion_finish(self, bw_ctx):
            self.events.append('completion')
            bw_ctx.success = True
            return HookSignal.DONE

    battle_wait = OrderedBattleWait()
    plan = BattleWaitPlan('setup_record', 'completion_finish')

    assert battle_wait.battle_wait_with_strategy(battle_wait_plan=plan) is True
    assert battle_wait.events == ['setup', 'screenshot', 'completion']


def test_custom_hook_is_resolved_and_executed_in_the_configured_sequence():
    class CustomBattleWait(BattleWait):
        def __init__(self):
            self.events = []

        def screenshot(self):
            pass

        def _bw_setup_record(self, bw_ctx):
            self.events.append('setup')
            return HookSignal.DONE

        def _bw_yyy_record(self, bw_ctx):
            self.events.append('yyy')
            return HookSignal.CONTINUE

        def _bw_completion_finish(self, bw_ctx):
            self.events.append('completion')
            bw_ctx.success = True
            return HookSignal.DONE

    battle_wait = CustomBattleWait()
    plan = BattleWaitPlan(
        'setup_record',
        'yyy_record',
        'completion_finish',
        sequence='yyy > completion > interrupt > success > failure > idle',
    )

    assert battle_wait.battle_wait_with_strategy(battle_wait_plan=plan) is True
    assert battle_wait.events == ['setup', 'yyy', 'completion']


def test_custom_sequence_controls_hook_order():
    plan = BattleWaitPlan(
        'yyy_default',
        sequence='failure > yyy > completion > interrupt > success > idle',
    )

    assert plan.sequence_function_names() == [
        '_bw_failure_default',
        '_bw_yyy_default',
        '_bw_completion_default',
        '_bw_interrupt_default',
        '_bw_success_default',
        '_bw_idle_default',
    ]


def test_custom_events_without_sequence_are_inserted_before_idle_in_argument_order():
    plan = BattleWaitPlan('yyy_default', 'abcd_edf')

    assert plan.sequence == 'completion>interrupt>success>failure>yyy>abcd>idle'


def test_dynamic_override_does_not_modify_the_default_plan():
    strategy = battle_wait_strategy('success_default')

    @strategy
    def battle_wait(owner, *, battle_wait_plan):
        return battle_wait_plan

    default_plan = strategy.battle_wait_plan

    overridden_plan = battle_wait(object(), random_click_swipt_enable=True)

    assert overridden_plan is not default_plan
    assert overridden_plan.randomclick == 'default'
    assert not hasattr(default_plan, 'randomclick')
    assert strategy.battle_wait_plan is default_plan


def test_dynamic_override_is_only_valid_for_the_current_call():
    strategy = battle_wait_strategy('success_default')

    @strategy
    def battle_wait(owner, *, battle_wait_plan):
        return battle_wait_plan

    battle_wait(object(), random_click_swipt_enable=True)
    plan_without_override = battle_wait(object(), random_click_swipt_enable=False)

    assert not hasattr(plan_without_override, 'randomclick')


# 验证单层装饰器保存自己的 options，with_options() 只在上下文内临时覆盖，退出后恢复。
def test_decorator_options_and_with_options_are_scoped_to_the_current_call():
    received_options = []
    decorator_options = {
        'completion': {'source': 'decorator'},
        'success': {'excludes': ['C_REWARD_1']},
    }
    context_options = {
        'success': {'excludes': ['C_END_MESSAGE_RIGHT_TOP']},
    }

    strategy = battle_wait_strategy(
        'setup_record', 'completion_record', options=decorator_options
    )

    class OptionBattleWait(BattleWait):
        def screenshot(self):
            pass

        def _bw_setup_record(self, bw_ctx):
            return HookSignal.DONE

        def _bw_completion_record(self, bw_ctx):
            received_options.append(bw_ctx.options)
            bw_ctx.success = True
            return HookSignal.DONE

        @strategy
        def battle_wait(self, *args, **kwargs):
            return self.battle_wait_with_strategy(*args, **kwargs)

    battle_wait = object.__new__(OptionBattleWait)

    assert battle_wait.battle_wait() is True
    assert received_options[-1] == decorator_options

    with strategy.with_options(context_options):
        assert battle_wait.battle_wait() is True
        assert received_options[-1] == {
            'completion': {'source': 'decorator'},
            'success': {'excludes': ['C_END_MESSAGE_RIGHT_TOP']},
        }
        strategy_text = str(strategy)
        assert 'options=' in strategy_text
        assert 'C_END_MESSAGE_RIGHT_TOP' in strategy_text

    assert battle_wait.battle_wait() is True
    assert received_options[-1] == decorator_options
    assert 'C_REWARD_1' in str(strategy)


def test_nested_context_restores_each_task_strategy_even_after_an_exception():
    def wait(owner, *, battle_wait_plan, options=None):
        return battle_wait_plan.success, options

    ordinary_wait = battle_wait_strategy()(wait)
    activity_wait = battle_wait_strategy(success='activity')(wait)
    outer = battle_wait_strategy(success='outer', options={'success': {'source': 'outer'}})
    inner = battle_wait_strategy(success='inner', options={'success': {'source': 'inner'}})

    # Merely constructing temporary strategies must not change existing tasks.
    assert ordinary_wait(object()) == ('default', None)
    assert activity_wait(object()) == ('activity', None)
    with outer:
        assert activity_wait(object()) == ('outer', {'success': {'source': 'outer'}})
        with pytest.raises(RuntimeError, match='interrupted'):
            with inner:
                assert ordinary_wait(object()) == ('inner', {'success': {'source': 'inner'}})
                raise RuntimeError('interrupted')
        assert activity_wait(object()) == ('outer', {'success': {'source': 'outer'}})

    assert ordinary_wait(object()) == ('default', None)
    assert activity_wait(object()) == ('activity', None)


def test_decorator_options_do_not_leak_between_tasks_or_calls():
    def wait(owner, *, battle_wait_plan, options):
        return options

    ordinary_options = {'success': {'excludes': ['C_REWARD_1']}}
    activity_options = {'success': {'excludes': ['C_END_ACTIVITY_REWARD']}}
    ordinary_wait = battle_wait_strategy(options=ordinary_options)(wait)
    activity_wait = battle_wait_strategy(success='activity', options=activity_options)(wait)

    assert ordinary_wait(object()) == ordinary_options
    assert activity_wait(object()) == activity_options
    ordinary_wait(object())['success']['excludes'].clear()
    assert ordinary_wait(object()) == ordinary_options
    assert activity_wait(object()) == activity_options
