from types import SimpleNamespace

import pytest

from module.base.cBezier import human_track
from module.device.method.windows_impl import Window


@pytest.mark.parametrize('start,end', [((10, 10), (10, 10)), ((10, 10), (10, 11)), ((10, 10), (10, 200))])
def test_degenerate_swipe_still_reaches_endpoint(start, end):
    points = human_track(start, end)
    assert points
    assert tuple(points[-1]) == end
    assert all(point[0] == 10 for point in points)


@pytest.mark.parametrize('size,expected', [((1280, 720), (640, 360)), ((1024, 576), (512, 288))])
def test_desktop_click_coordinates_follow_virtual_client_size(size, expected):
    window = SimpleNamespace(screenshot_size=(1280, 720), desktop_client_size_virtual=lambda: size)
    assert Window.desktop_message_coord(window, 640, 360) == expected
