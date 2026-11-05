import pytest

from tasks.WantedQuests.script_task import _read_location_info


@pytest.mark.parametrize('first,retry,expected', [
    ('荒川之怒（数量：2）', None, ('荒川之怒', '2')),
    ('数量:2)', '荒川之怒(数量:2)', ('荒川之怒', '2')),
    ('荒川之怒', '', None),
])
def test_location_read_preserves_width_and_shared_rule(first, retry, expected):
    seen = []
    original = (20, 30, 150, 35)

    class Rule:
        roi = original

        def ocr(self, image):
            seen.append(tuple(self.roi))
            return first if len(seen) == 1 else retry

    rule = Rule()
    match = _read_location_info(rule, None)
    assert (match.groups() if match else None) == expected
    assert seen == ([original] if retry is None else [original, (20, 37, 150, 21)])
    assert rule.roi == original
