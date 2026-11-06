
from buggy_code import factorial, fibonacci, recursive_sum


def test_factorial():
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(5) == 120
    assert factorial(7) == 5040


def test_fibonacci():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(5) == 5
    assert fibonacci(7) == 13


def test_recursive_sum():
    assert recursive_sum([]) == 0
    assert recursive_sum([5]) == 5
    assert recursive_sum([1, 2, 3, 4]) == 10
    assert recursive_sum([-2, 3, -1]) == 0
