"""Replay chapter selection against the new ascending chapter list."""
from types import SimpleNamespace

import pytest

from module.exception import GameStuckError
from tasks.Exploration.base import BaseExploration
from tasks.Exploration.config import ExplorationLevel
from tasks.Exploration.page import page_mainline


class ChapterListReplay(BaseExploration):
    # The supplied 1280x720 screenshot has chapter headings 106 pixels apart.
    CHAPTER_HEIGHT = 106
    CHAPTERS = [level.value for level in ExplorationLevel]
    MAX_OFFSET = len(CHAPTERS) * CHAPTER_HEIGHT - 337

    def __init__(self, monkeypatch, target, *, at_bottom=False, blocked=False,
                 empty_frames=()):
        self.config = SimpleNamespace(exploration=SimpleNamespace(
            exploration_config=SimpleNamespace(exploration_level=target),
        ))
        self.offset = self.MAX_OFFSET if at_bottom else 0
        self.blocked = blocked
        self.empty_frames = empty_frames
        self.frames = 0
        self.swipes = []
        self.clicked = []
        self.entrance_open = False
        self.interval_timer = {}
        self.device = SimpleNamespace(
            image=None, swipe=self.drag, click_record_clear=lambda: None,
        )
        self.O_E_EXPLORATION_LEVEL_NUMBER = SimpleNamespace(
            keyword='', detect_and_ocr=self.recognize_chapters,
        )
        monkeypatch.setattr('tasks.Exploration.base.time.sleep', lambda _: None)
        monkeypatch.setattr('module.atom.swipe.random_normal_distribution_int',
                            lambda low, high: (low + high) // 2)

    def visible_chapters(self):
        return [name for index, name in enumerate(self.CHAPTERS)
                if 206 <= 215 + index * self.CHAPTER_HEIGHT - self.offset <= 543 - 28]

    def recognize_chapters(self, image):
        if self.frames in self.empty_frames:
            return []
        return [SimpleNamespace(ocr_text=text) for text in self.visible_chapters()]

    def goto_page(self, page):
        assert page is page_mainline

    def screenshot(self):
        self.frames += 1
        assert self.frames < 40, 'Chapter selection failed to terminate'

    def appear(self, asset):
        return asset is self.I_E_EXPLORATION_CLICK and self.entrance_open

    def appear_then_click(self, asset, **kwargs):
        return False

    def drag(self, p1, p2, control_name):
        # Use the production swipe coordinates, not their potentially ambiguous names.
        for x, y in (p1, p2):
            assert 1064 <= x < 1185 and 206 <= y < 543
        self.swipes.append((p1, p2))
        if not self.blocked:
            self.offset = max(0, min(self.MAX_OFFSET, self.offset + p1[1] - p2[1]))

    def ocr_appear_click(self, rule):
        if rule.keyword not in self.visible_chapters():
            return False
        self.clicked.append(rule.keyword)
        self.entrance_open = True
        return True

    def wait_until_appear(self, asset, **kwargs):
        assert self.appear(asset)

    def is_in_room(self):
        return False


@pytest.mark.parametrize('at_bottom', [False, True], ids=['from-top', 'from-bottom'])
@pytest.mark.parametrize('target', list(ExplorationLevel), ids=lambda level: level.name)
def test_every_chapter_is_reachable_within_the_swipe_limit(monkeypatch, target, at_bottom):
    task = ChapterListReplay(monkeypatch, target, at_bottom=at_bottom)

    assert task.open_expect_level() is True
    assert task.clicked == [target]
    assert len(task.swipes) < 15


def test_reported_first_three_chapters_scroll_toward_chapter_28(monkeypatch):
    task = ChapterListReplay(monkeypatch, '第二十八章')
    assert task.visible_chapters() == ['第一章', '第二章', '第三章']

    assert task.open_expect_level() is True
    assert task.swipes
    assert all(start[1] > end[1] for start, end in task.swipes)
    assert task.clicked == ['第二十八章']


def test_visible_chapter_is_selected_without_swiping(monkeypatch):
    task = ChapterListReplay(monkeypatch, '第二章')

    assert task.open_expect_level() is True
    assert task.swipes == []


def test_temporary_ocr_miss_preserves_scroll_direction(monkeypatch):
    task = ChapterListReplay(monkeypatch, '第一章', at_bottom=True, empty_frames={2, 3})

    assert task.open_expect_level() is True
    assert all(start[1] < end[1] for start, end in task.swipes)
    assert task.clicked == ['第一章']


def test_unresponsive_chapter_list_still_hits_the_swipe_limit(monkeypatch):
    task = ChapterListReplay(monkeypatch, '第二十八章', blocked=True)

    with pytest.raises(GameStuckError, match='Swiped too many times'):
        task.open_expect_level()

    assert len(task.swipes) == 15
    assert task.clicked == []
