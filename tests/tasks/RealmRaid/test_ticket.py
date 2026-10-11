from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from module.exception import GameOcrError
from tasks.RealmRaid import script_task


def frame(reading=(23, 7, 30), *, page=True, battle=False, reward=False):
    return SimpleNamespace(reading=reading, page=page, battle=battle, reward=reward)


def ticket_replay(frames):
    task = object.__new__(script_task.ScriptTask)
    frames = iter(frames)
    task.device = SimpleNamespace(image=None, save_screenshot=Mock())

    def screenshot():
        task.device.image = next(frames)

    def appear(asset, **kwargs):
        current = task.device.image
        if asset is task.I_BATTLE_INFO:
            return current.battle
        if asset is task.I_CHECK_REALM_RAID or asset is task.I_BACK_RED:
            return current.page
        if asset is task.I_SOUL_RAID:
            return current.reward
        return False

    task.screenshot = Mock(side_effect=screenshot)
    task.appear = Mock(side_effect=appear)
    task.appear_then_click = Mock(side_effect=appear)
    task.wait_until_appear = Mock(side_effect=AssertionError('Unbounded page wait'))
    task.O_NUMBER = SimpleNamespace(ocr=Mock(side_effect=lambda image: image.reading))
    task.O_TEXT = SimpleNamespace(ocr=Mock(side_effect=AssertionError('Unbounded text wait')))
    return task


@pytest.fixture
def sleep(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(script_task.time, 'sleep', sleep)
    return sleep


@pytest.mark.parametrize('reading,base,expected', [
    ((0, 30, 30), 0, False),
    ((1, 29, 30), 0, True),
    ((30, 0, 30), 0, True),
    ((5, 25, 30), 6, False),
    ((5, 25, 30), 5, True),
    ((1, 29, 30), -1, True),
    ((1, 29, 30), 31, True),
])
def test_valid_ticket_count_controls_empty_and_minimum(reading, base, expected, sleep):
    task = ticket_replay([frame(reading)])
    assert task.check_ticket(base) is expected
    assert task.screenshot.call_count == 1
    sleep.assert_not_called()
    task.device.save_screenshot.assert_not_called()


@pytest.mark.parametrize('invalid', [
    (0, 0, 0), (0, 3, 3), (23, 7, 0), (31, -1, 30), (-1, 31, 30), (23, 0, 30),
])
def test_invalid_ocr_retries_with_a_new_frame(invalid, sleep):
    first, second = frame(invalid), frame()
    task = ticket_replay([first, second])
    assert task.check_ticket() is True
    assert task.O_NUMBER.ocr.call_args_list == [call(first), call(second)]
    sleep.assert_called_once_with(1)
    task.device.save_screenshot.assert_not_called()


def test_tenth_retry_can_still_succeed(sleep):
    task = ticket_replay([frame((0, 0, 0)) for _ in range(10)] + [frame()])
    assert task.check_ticket() is True
    assert task.screenshot.call_count == 11
    assert sleep.call_args_list == [call(1)] * 10
    task.device.save_screenshot.assert_not_called()


@pytest.mark.parametrize('save_fails', [False, True])
def test_exhausted_retries_save_last_failed_frame_and_raise_restart_error(sleep, save_fails):
    frames = [frame((0, 0, 0)) for _ in range(11)]
    task = ticket_replay(frames)
    if save_fails:
        task.device.save_screenshot.side_effect = OSError('Disk unavailable')
    with pytest.raises(GameOcrError, match='after 10 retries'):
        task.check_ticket()
    assert task.screenshot.call_count == task.O_NUMBER.ocr.call_count == 11
    assert sleep.call_args_list == [call(1)] * 10
    assert task.device.image is frames[-1]
    task.device.save_screenshot.assert_called_once_with(genre='realm_raid_ticket_ocr', interval=0)


@pytest.mark.parametrize('page,battle', [(False, False), (False, True), (True, True)])
def test_wrong_screen_does_not_read_tickets_or_click_rewards(page, battle, sleep):
    first, second = frame((0, 30, 30), page=page, battle=battle), frame()
    task = ticket_replay([first, second])
    assert task.check_ticket() is True
    task.O_NUMBER.ocr.assert_called_once_with(second)
    sleep.assert_called_once_with(1)


@pytest.mark.parametrize('battle', [False, True])
def test_persistent_wrong_screen_uses_the_same_bounded_recovery(battle, sleep):
    task = ticket_replay([frame(page=False, battle=battle) for _ in range(11)])
    with pytest.raises(GameOcrError):
        task.check_ticket()
    task.O_NUMBER.ocr.assert_not_called()
    assert task.screenshot.call_count == 11
    assert sleep.call_args_list == [call(1)] * 10
    assert task.device.save_screenshot.call_count == 1


def test_reward_is_claimed_even_when_it_covers_the_page_anchor(sleep):
    reward, ready = frame(page=False, reward=True), frame()
    task = ticket_replay([reward, ready])
    assert task.check_ticket() is True
    task.O_NUMBER.ocr.assert_called_once_with(ready)
    sleep.assert_called_once_with(1)


def test_reward_match_is_ignored_while_still_in_battle(sleep):
    task = ticket_replay([frame(battle=True, reward=True)])
    assert task.reward_detect_click() is False
    task.appear_then_click.assert_not_called()


def test_reward_detection_does_not_wait_for_banner_text_to_disappear(sleep):
    task = ticket_replay([frame()])
    assert task.reward_detect_click() is False
    assert task.screenshot.call_count == 1
    task.O_TEXT.ocr.assert_not_called()
    task.wait_until_appear.assert_not_called()


def test_legacy_ticket_check_uses_the_same_recovery(sleep):
    task = ticket_replay([frame((0, 0, 0)), frame()])
    assert task.is_ticket() is True
    assert task.O_NUMBER.ocr.call_count == 2
