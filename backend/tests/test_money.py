from decimal import Decimal

import pytest

from app.core.money import money_to_str, quantize_money


def test_quantize_money_valid() -> None:
    assert quantize_money("1250") == Decimal("1250.00")
    assert quantize_money("1250.456") == Decimal("1250.46")  # ROUND_HALF_UP
    assert quantize_money("1250.454") == Decimal("1250.45")
    assert quantize_money(100) == Decimal("100.00")
    assert quantize_money(Decimal("0.00")) == Decimal("0.00")


def test_quantize_money_rejects_float() -> None:
    with pytest.raises(TypeError, match="Floats are strictly prohibited"):
        quantize_money(1250.50)  # type: ignore[arg-type]


def test_money_to_str() -> None:
    assert money_to_str(Decimal("1000")) == "1000.00"
    assert money_to_str(Decimal("0")) == "0.00"
    assert money_to_str(Decimal("45.678")) == "45.68"
