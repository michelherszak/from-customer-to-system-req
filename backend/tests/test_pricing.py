from decimal import Decimal
from kusys.pricing.engine import PricingEngine, PricedWorkPackage, Rate


def test_US14_AC_08_equal_attribution_and_rounding():
    result = PricingEngine().calculate(
        [PricedWorkPackage("P1", "R", 1, ("r1", "r2", "r3"))],
        [Rate("R", Decimal("60"), Decimal("100"))],
        [],
        {"r1": None, "r2": None, "r3": None},
        vat_percent=Decimal("0"),
    )
    assert sum((x.sales_eur for x in result.attribution), Decimal("0")) == Decimal("100.00")
    assert result.net_eur == Decimal("100.00")


def test_US14_AC_08_weighted_attribution():
    result = PricingEngine().calculate(
        [PricedWorkPackage("P1", "R", 10, ("r1", "r2"), (Decimal("3"), Decimal("1")))],
        [Rate("R", Decimal("50"), Decimal("100"))],
        [],
        {"r1": Decimal("1000"), "r2": Decimal("1000")},
        vat_percent=Decimal("0"),
    )
    by_id = {x.requirement_id: x for x in result.attribution}
    assert by_id["r1"].sales_eur == Decimal("750.00")
    assert by_id["r2"].sales_eur == Decimal("250.00")
