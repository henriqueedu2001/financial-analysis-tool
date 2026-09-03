from decimal import Decimal

import pytest

from finance.money import InvalidMoney, cents_to_decimal, decimal_to_cents


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.10", 10),
        ("0.20", 20),
        ("1234.56", 123456),
        ("-2000.00", -200000),
        (Decimal("6000.00"), 600000),
        (5, 500),
    ],
)
def test_decimal_money_is_converted_to_exact_integer_cents(value, expected):
    assert decimal_to_cents(value) == expected
    assert cents_to_decimal(expected) == Decimal(str(expected)) / 100


def test_float_is_rejected_before_it_can_reach_persistence():
    with pytest.raises(InvalidMoney, match="float is not accepted"):
        decimal_to_cents(0.1 + 0.2)


@pytest.mark.parametrize("value", ["1.001", "NaN", "Infinity", "not-money", True])
def test_invalid_monetary_values_are_rejected(value):
    with pytest.raises(InvalidMoney):
        decimal_to_cents(value)
