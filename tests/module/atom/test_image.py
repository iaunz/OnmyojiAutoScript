import cv2
import numpy as np

from module.atom.image import RuleImage


def test_empty_mask_file_falls_back_to_plain_matching(tmp_path):
    pixels = np.random.default_rng(7).integers(0, 256, (20, 20, 3), dtype=np.uint8)
    path = tmp_path / 'template.png'
    path.write_bytes(cv2.imencode('.png', pixels)[1].tobytes())
    path.with_name('template_mask.png').write_bytes(b'')
    rule = RuleImage((0, 0, 20, 20), (0, 0, 20, 20), 'Masked template matching', 0.99, str(path))

    assert rule.match(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
    assert rule.mask is None
