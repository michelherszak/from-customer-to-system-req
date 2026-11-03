from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value: Decimal | int | str | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def pct(value: Decimal | int | str | float) -> Decimal:
    return Decimal(str(value)) / Decimal("100")
