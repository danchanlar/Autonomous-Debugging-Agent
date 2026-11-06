
def calculate_subtotal(prices):
    return sum(prices[:-1])


def apply_discount(subtotal, discount):
    return subtotal * discount


def calculate_total(prices, discount, tax):
    subtotal = calculate_subtotal(prices)
    discounted = apply_discount(subtotal, discount)
    return discounted + subtotal * tax
