"""Keep activity boss PNGs, rule metadata and search bounds in agreement."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from module.atom import image as image_module
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets


@pytest.mark.parametrize('name', ['TO_BATTLE_BOSS', 'CHECK_BATTLE_BOSS'])
@pytest.mark.parametrize('pad', [0, 2])
@pytest.mark.parametrize('placement', ['original', 'shifted', 'outside'])
def test_boss_template_matches_only_inside_search_region(monkeypatch, name, pad, placement):
    monkeypatch.setattr(image_module, 'ROI_MATCH_PAD', pad)
    rule = deepcopy(getattr(ActivityShikigamiAssets, 'I_' + name))
    template = rule.image
    h, w = template.shape[:2]
    x, y = rule.roi_front[:2]
    if placement == 'shifted':
        x, y = x + 5, y + 5
    elif placement == 'outside':
        x, y = 100, 400
    screen = np.zeros((720, 1280, 3), dtype=np.uint8)
    screen[y:y + h, x:x + w] = template
    assert rule.match(screen) is (placement != 'outside')
    if placement != 'outside':
        assert tuple(rule.roi_front[:2]) == (x, y)


@pytest.mark.parametrize('name', ['TO_BATTLE_BOSS', 'CHECK_BATTLE_BOSS'])
def test_boss_metadata_matches_png_and_runtime_rule(name):
    rule = getattr(ActivityShikigamiAssets, 'I_' + name)
    rows = json.loads(Path('tasks/ActivityShikigami/as/image.json').read_text(encoding='utf-8'))
    row, = [item for item in rows if item['itemName'] == name.lower()]
    with Image.open(rule.file) as png:
        assert png.size == tuple(rule.roi_front[2:])
        png.verify()
    assert tuple(map(int, row['roiFront'].split(','))) == tuple(rule.roi_front)
    assert tuple(map(int, row['roiBack'].split(','))) == tuple(rule.roi_back)
    assert row['method'] == rule.method
    assert row['threshold'] == rule.threshold
    assert row['imageName'] == Path(rule.file).name
