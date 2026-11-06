
def factorial(n):
    if n == 0:
        return 1
    elif n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    else:
        return n * factorial(n - 1)


def fibonacci(n):
    if n <= 1:
        return n
    elif n == 2:
        return 1
    else:
        return fibonacci(n - 1) + fibonacci(n - 2)


def recursive_sum(numbers):
    if len(numbers) == 0:
        return 0
    return numbers[0] + recursive_sum(numbers[1:])
