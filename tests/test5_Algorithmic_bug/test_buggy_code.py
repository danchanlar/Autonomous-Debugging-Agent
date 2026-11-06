from buggy_code import binary_search


def test_first_element():
    assert binary_search([1, 3, 5, 7, 9], 1) == 0


def test_middle_element():
    assert binary_search([1, 3, 5, 7, 9], 5) == 2


def test_last_element():
    assert binary_search([1, 3, 5, 7, 9], 9) == 4


def test_missing_element():
    assert binary_search([1, 3, 5, 7, 9], 6) == -1


def test_single_element():
    assert binary_search([5], 5) == 0


def test_empty_list():
    assert binary_search([], 5) == -1