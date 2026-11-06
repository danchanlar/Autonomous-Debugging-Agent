from buggy_code import BankAccount


def test_initial_balance():
    account = BankAccount(100)
    assert account.get_balance() == 100


def test_deposit():
    account = BankAccount(100)
    account.deposit(50)
    assert account.get_balance() == 150


def test_withdraw():
    account = BankAccount(100)
    assert account.withdraw(40) is True
    assert account.get_balance() == 60


def test_insufficient_funds():
    account = BankAccount(100)
    assert account.withdraw(150) is False
    assert account.get_balance() == 100


def test_multiple_operations():
    account = BankAccount(100)
    account.deposit(50)
    account.withdraw(30)
    assert account.get_balance() == 120