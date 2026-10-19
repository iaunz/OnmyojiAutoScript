from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from module.atom import image as image_module
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets


@pytest.mark.parametrize('pad', [0, 2])
@pytest.mark.parametrize('position,expected', [((742, 558), True), ((549, 567), True), ((100, 100), False)])
def test_cropped_invitation_template_covers_both_dialog_positions(monkeypatch, pad, position, expected):
    monkeypatch.setattr(image_module, 'ROI_MATCH_PAD', pad)
    rule = deepcopy(GeneralInviteAssets.I_INVITE_ENSURE)
    template = rule.image
    height, width = template.shape[:2]
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    x, y = position
    screen[y:y + height, x:x + width] = template
    assert rule.match(screen) is expected
    if expected:
        assert tuple(rule.roi_front[:2]) == position


def test_invitation_metadata_keeps_crop_and_search_region_consistent():
    rule = GeneralInviteAssets.I_INVITE_ENSURE
    rows = json.loads(Path('tasks/Component/GeneralInvite/gi/image.json').read_text(encoding='utf-8'))
    row, = [entry for entry in rows if entry['itemName'] == 'invite_ensure']
    with Image.open(rule.file) as template:
        assert template.size == (68, 32) == tuple(rule.roi_front[2:])
        template.verify()
    assert tuple(map(int, row['roiFront'].split(','))) == tuple(rule.roi_front)
    assert tuple(map(int, row['roiBack'].split(','))) == tuple(rule.roi_back)
    assert row['threshold'] == rule.threshold
    assert row['method'] == rule.method
    assert row['imageName'] == Path(rule.file).name
