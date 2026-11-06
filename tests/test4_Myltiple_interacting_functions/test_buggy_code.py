
from buggy_code import calculate_subtotal, apply_discount, calculate_total


def test_calculate_subtotal():
    assert calculate_subtotal([]) == 0
    assert calculate_subtotal([10]) == 10
    assert calculate_subtotal([10, 20, 30]) == 60


def test_apply_discount():
    assert apply_discount(100, 0) == 100
    assert apply_discount(100, 0.2) == 80
    assert apply_discount(200, 0.5) == 100


def test_calculate_total():
    assert calculate_total([100], 0, 0) == 100
    assert calculate_total([100], 0.2, 0) == 80
    assert calculate_total([100], 0, 0.1) == 110
    assert calculate_total([50, 50], 0.1, 0.2) == 108
