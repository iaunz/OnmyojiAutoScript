from types import SimpleNamespace

import pytest

from module.base import timer
from module.exception import GamePageUnknownError
from tasks.GameUi.navigator import GameUi
from tasks.GameUi.page_definition import Page
from tasks.GameUi.session import NavigatorSession


def make_page(key):
    return Page(lambda task: task.screen == key, key=key, name=key,
                category='global', register=False)


class NavigationReplay(GameUi):
    def __init__(self, monkeypatch, pages, *, blocked=False):
        self.navigator = NavigatorSession(task_category='global')
        self.navigator.bootstrap(pages)
        self.screen = pages[0].key
        self.navigator.current_page = self.navigator.pages[self.screen]
        self.now = 100.0
        self.frames = 0
        self.attempts = []
        self.blocked = blocked
        monkeypatch.setattr(timer, 'time', SimpleNamespace(time=lambda: self.now))

    def screenshot(self):
        self.now += 1
        self.frames += 1
        assert self.frames < 50, 'Replanning kept navigation alive without progress'

    def maybe_screenshot(self, skip_first_screenshot=True):
        if not skip_first_screenshot:
            self.screenshot()

    def close_unknown_pages(self, **kwargs):
        return False

    def _execute_action(self, action, **kwargs):
        return action(self)

    def _execute_transition(self, transition):
        self.screenshot()
        self.attempts.append(transition.key)
        if self.blocked:
            self.navigator.add_penalty(transition)
            return False
        self.screen = transition.destination.key
        self.navigator.current_page = transition.destination
        return True


def test_failed_alternative_routes_still_reach_navigation_timeout(monkeypatch):
    source, target = make_page('source'), make_page('target')
    source.connect(target, lambda task: True, key='first')
    source.connect(target, lambda task: True, key='second')
    task = NavigationReplay(monkeypatch, [source, target], blocked=True)

    with pytest.raises(GamePageUnknownError, match='Cannot goto page'):
        task.goto_page(target, timeout=5)

    assert {'first', 'second'} <= set(task.attempts)
    assert task.frames < 15


def test_navigation_accepts_alternate_page_and_runs_arrival_hook_once(monkeypatch):
    alternate, target = make_page('alternate'), make_page('target')
    entered = []
    alternate.add_enter_success_hooks(lambda task: entered.append(task.screen))
    task = NavigationReplay(monkeypatch, [alternate, target])

    assert task.goto_page(target, accepted_pages=(alternate,)) is True
    assert task.navigator.current_page.key == alternate.key
    assert entered == ['alternate']
    assert task.attempts == []


def test_navigation_arrives_after_successful_transition(monkeypatch):
    source, target = make_page('source'), make_page('target')
    source.connect(target, lambda task: True, key='direct')
    task = NavigationReplay(monkeypatch, [source, target])

    assert task.goto_page(target) is True
    assert task.navigator.current_page.key == target.key
    assert task.attempts == ['direct']


def test_session_transition_changes_do_not_leak_to_other_tasks():
    source, target = make_page('source'), make_page('target')
    first, second = NavigatorSession('global'), NavigatorSession('global')
    first.bootstrap([source, target])
    second.bootstrap([source, target])
    first.resolve_page(source).connect(first.resolve_page(target), lambda task: True)

    assert len(first.resolve_page(source).transitions) == 1
    assert second.resolve_page(source).transitions == []
    assert source.transitions == []
