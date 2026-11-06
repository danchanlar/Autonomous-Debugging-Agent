
from buggy_code import calculate_average, find_maximum, is_even


def test_average():
    assert calculate_average([2, 4, 6]) == 4
    assert calculate_average([10, 20]) == 15


def test_maximum():
    assert find_maximum([3, 8, 2]) == 8
    assert find_maximum([-5, -2, -9]) == -2


def test_even():
    assert is_even(4) is True
    assert is_even(7) is False
