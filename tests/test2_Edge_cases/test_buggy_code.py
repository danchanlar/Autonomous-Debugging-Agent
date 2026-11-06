
from buggy_code import calculate_average, safe_divide, clamp


def test_average():
    assert calculate_average([2, 4, 6]) == 4
    assert calculate_average([]) == 0
    assert calculate_average([-2, -4]) == -3


def test_safe_divide():
    assert safe_divide(10, 2) == 5
    assert safe_divide(5, 0) is None
    assert safe_divide(0, 5) == 0


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-3, 0, 10) == 0
    assert clamp(15, 0, 10) == 10
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10
