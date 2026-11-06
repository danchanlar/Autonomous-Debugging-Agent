def calculate_average(numbers):
    total = 0
    for number in numbers:
        total += number
    return total / len(numbers)


def find_maximum(numbers):
    maximum = numbers[0]  # Initialize maximum to the first element
    for number in numbers:
        if number > maximum:
            maximum = number
    return maximum


def is_even(number):
    return number % 2 == 0


def test_average():
    assert calculate_average([2, 4, 6]) == 4


def test_maximum():
    assert find_maximum([3, 8, 2]) == 8


def test_even():
    assert is_even(4) is True