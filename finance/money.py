"""Deterministic helpers for converting monetary values to integer cents."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


class InvalidMoney(ValueError):
    """Raised when a monetary value cannot be represented as cents."""


def decimal_to_cents(value: Decimal | str | int) -> int:
    """Convert a decimal monetary value into integer cents.

    Floats are intentionally rejected so that binary floating-point errors never
    enter the persistent representation.
    """

    if isinstance(value, float) or isinstance(value, bool):
        raise InvalidMoney("use Decimal, string or integer; float is not accepted")

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidMoney(f"invalid monetary value: {value!r}") from exc

    if not decimal_value.is_finite():
        raise InvalidMoney("monetary value must be finite")

    quantized = decimal_value.quantize(CENT, rounding=ROUND_HALF_UP)
    if quantized != decimal_value:
        raise InvalidMoney("monetary value may have at most two decimal places")
    return int(quantized * 100)


def cents_to_decimal(cents: int) -> Decimal:
    """Convert integer cents to an exact two-decimal Decimal."""

    if isinstance(cents, bool) or not isinstance(cents, int):
        raise InvalidMoney("cents must be an integer")
    return (Decimal(cents) / 100).quantize(CENT)
