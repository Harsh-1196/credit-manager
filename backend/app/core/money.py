from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def quantize_money(amount: Decimal | str | int) -> Decimal:
    """
    Quantize monetary values to 2 decimal places using ROUND_HALF_UP.
    Never accepts floats.
    """
    if isinstance(amount, float):
        raise TypeError("Floats are strictly prohibited for monetary calculations. Use Decimal or str.")
    d = Decimal(str(amount))
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def money_to_str(amount: Decimal) -> str:
    """
    Serialize Decimal to exact two-decimal string representation (e.g. '1250.00').
    """
    return f"{quantize_money(amount):.2f}"
