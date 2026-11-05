"""Exercise bounded island entry without a game or OCR service."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from module.exception import GameStuckError
from tasks.SixRealms.common import MoonSeaType
from tasks.SixRealms.moon_sea.map import MoonSeaMap


class OfflineMoonSea(MoonSeaMap):
    def __init__(self, enter_after=None, cancel_visible=False):
        # Skip Config/Device initialization, retaining the production click method.
        self.device = SimpleNamespace(click=self.record_click)
        self.now = 100.0
        self.frames = 0
        self.interval_timer = {}
        self.events = []
        self.enter_after = enter_after
        self.cancel_visible = cancel_visible

    def record_click(self, x, y, control_name):
        self.events.append((self.now, control_name))

    def screenshot(self):
        self.now += 0.25
        self.frames += 1
        if self.frames > 80:
            raise AssertionError("Island entry exceeded its timeout")

    def in_main(self):
        return self.enter_after is None or len(self.events) < self.enter_after

    def appear(self, rule, **kwargs):
        if rule is self.I_BACK_EXIT:
            return not self.in_main()
        if rule is self.I_UI_CANCEL:
            return self.cancel_visible
        return False

    def appear_then_click(self, rule, **kwargs):
        if not self.appear(rule):
            return False
        self.click(rule)
        return True


class IslandEntryTests(unittest.TestCase):
    def enter_unknown(self, task):
        with patch("module.base.timer.time.time", side_effect=lambda: task.now):
            task.enter_island(MoonSeaType.island100, (0, 0, 0, 0))

    def test_entry_stops_without_clicking_when_already_inside(self):
        task = OfflineMoonSea(enter_after=0)
        self.enter_unknown(task)
        self.assertEqual(task.events, [])

    def test_known_island_tracks_height_without_switching_columns(self):
        task = OfflineMoonSea(enter_after=2)
        left = (288, 280, 20, 90)
        frames = [[(1040, 300, 20, 90), left],
                  [(288, 320, 20, 90), (1040, 340, 20, 90)]]
        with patch.object(task, "_marker_boxes", side_effect=frames), \
                patch.object(task, "click", wraps=task.click) as click, \
                patch("module.base.timer.time.time", side_effect=lambda: task.now):
            task.enter_island(MoonSeaType.island104, left)
        self.assertEqual([call.args[0].roi_front for call in click.call_args_list],
                         [(268, 340, 60, 60), (268, 380, 60, 60)])

    def test_decide_keeps_ocr_target_without_a_nearby_marker(self):
        task = OfflineMoonSea()
        roi = (288, 280, 22, 80)
        for target, marker, prefer_store in (
            (MoonSeaType.island104, MoonSeaType.island104, False),
            (MoonSeaType.island104, MoonSeaType.island103, False),
            (MoonSeaType.island101, MoonSeaType.island101, True),
        ):
            ocr = (target, 9, roi)
            boxes = {marker: [(1040, 300, 20, 90)]}
            with self.subTest(target=target, marker=marker, prefer_store=prefer_store), \
                    patch.object(task, "_read_map_ocr", return_value=ocr), \
                    patch.object(task, "_marker_boxes", side_effect=lambda kind: boxes.get(kind, [])):
                self.assertEqual(task.decide(prefer_store=prefer_store), ocr)

    def test_disappearing_marker_times_out_without_clicking_adjacent_island(self):
        task = OfflineMoonSea()
        adjacent = (290, 330, 20, 90)
        with patch.object(task, "_marker_boxes", return_value=[adjacent]), \
                patch.object(task, "_read_map_ocr", return_value=(MoonSeaType.island104, 9, adjacent)), \
                patch("module.base.timer.time.time", side_effect=lambda: task.now):
            with self.assertRaisesRegex(GameStuckError, "Enter island104 timeout"):
                task.enter_island(MoonSeaType.island104, (1040, 310, 20, 90))
        self.assertEqual(task.events, [])

    def test_entry_cycles_in_order_with_one_shared_interval(self):
        task = OfflineMoonSea(enter_after=8)
        self.enter_unknown(task)
        self.assertEqual(
            [name for _, name in task.events],
            [f"island_enter_{number}" for number in (1, 2, 3, 4, 5, 6, 1, 2)],
        )
        for earlier, later in zip(task.events, task.events[1:]):
            self.assertGreaterEqual(later[0] - earlier[0], 1)

    def test_unrecognized_page_times_out_instead_of_clicking_forever(self):
        task = OfflineMoonSea()
        with self.assertRaisesRegex(GameStuckError, "Enter unknown island timeout"):
            self.enter_unknown(task)
        self.assertGreater(task.now, 115)
        self.assertLessEqual(task.now, 115.25)
        self.assertLessEqual(len(task.events), 15)

    def test_cancel_popup_obeys_interval_and_does_not_reset_timeout(self):
        task = OfflineMoonSea(cancel_visible=True)
        with self.assertRaises(GameStuckError):
            self.enter_unknown(task)
        self.assertTrue(task.events)
        self.assertTrue(all(name == task.I_UI_CANCEL.name for _, name in task.events))
        self.assertLessEqual(task.now, 115.25)
        for earlier, later in zip(task.events, task.events[1:]):
            self.assertGreaterEqual(later[0] - earlier[0], 1)

    def test_recognized_island_stops_or_times_out(self):
        for enter_after in (0, 2, None):
            with self.subTest(enter_after=enter_after):
                task = OfflineMoonSea(enter_after=enter_after)
                with patch.object(task, "_marker_boxes", return_value=[(100, 100, 40, 40)]), \
                        patch("module.base.timer.time.time", side_effect=lambda: task.now):
                    if enter_after is None:
                        with self.assertRaises(GameStuckError):
                            task.enter_island(MoonSeaType.island101, (100, 100, 40, 40))
                    else:
                        task.enter_island(MoonSeaType.island101, (100, 100, 40, 40))
                        self.assertEqual(len(task.events), enter_after)
                self.assertLessEqual(task.now, 115.25)
                for earlier, later in zip(task.events, task.events[1:]):
                    self.assertGreaterEqual(later[0] - earlier[0], 2.5)

    def test_random_entry_uses_shared_interval_and_stops(self):
        task = OfflineMoonSea(enter_after=5)
        with patch("module.base.timer.time.time", side_effect=lambda: task.now):
            task.entry_island_random()
        self.assertEqual([name for _, name in task.events],
                         [f"island_enter_{n}" for n in (4, 5, 6, 4, 5)])
        for earlier, later in zip(task.events, task.events[1:]):
            self.assertGreaterEqual(later[0] - earlier[0], 1)

    def test_random_entry_timeout_including_persistent_cancel(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                task = OfflineMoonSea(cancel_visible=cancel)
                with patch("module.base.timer.time.time", side_effect=lambda: task.now):
                    with self.assertRaises(GameStuckError):
                        task.entry_island_random()
                self.assertLessEqual(task.now, 115.25)
                self.assertLessEqual(len(task.events), 15)
                if cancel:
                    self.assertTrue(all(name == task.I_UI_CANCEL.name for _, name in task.events))


if __name__ == "__main__":
    unittest.main()
