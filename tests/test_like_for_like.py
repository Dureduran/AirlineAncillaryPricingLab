"""The test compares Current Pricing and the New Model on the same bookings.

A booking whose item Business Rules make free or unavailable is paid for under
neither system. These tests fail if either side is credited on such a booking.
"""

import itertools

import pandas as pd
import pytest

from app.pricing_test_results import METRIC_ROWS, TEST_RESULTS_BASIS, results_view
from business_rules import (
    FREE_REASONS,
    NOT_CHARGEABLE_REASONS,
    UNAVAILABLE_REASONS,
    apply_business_rules,
    not_chargeable_reason,
)
from lab.constants import CABINS, FARE_TYPES, FIXTURE_BOOKING, LOYALTY, PRODUCTS
from lab.paths import STATE_DIR
from monitor.test_results import chargeable_mask, summarise
from new_model.recommend import recommend

SIMULATED = STATE_DIR / "simulated_offers.parquet"

# One booking for each way Business Rules take the price away.
NOT_CHARGEABLE_BOOKINGS = {
    "included_in_fare": dict(FIXTURE_BOOKING, fare_type="Deluxe"),
    "loyalty_complimentary": dict(FIXTURE_BOOKING, loyalty="Gold"),
    "no_inventory": dict(FIXTURE_BOOKING, remaining_extra_legroom=0),
}


def _mixed_offers() -> pd.DataFrame:
    """Two chargeable bookings and three that are free or unavailable.

    The free rows carry a Current Pricing quote and a purchase chance, as the
    lab's data did before the comparison was made like-for-like.
    """
    return pd.DataFrame(
        {
            "current_price": [120.0, 90.0, 80.0, 150.0, 130.0],
            "customer_price": [100.0, 110.0, 0.0, 0.0, None],
            "p_buy_current": [0.50, 0.40, 0.30, 0.60, 0.70],
            "p_buy_new": [0.70, 0.30, 0.0, 0.0, 0.0],
            "offered": [True, True, False, False, False],
            "rule_reason_codes": [
                ["rules_passed"],
                ["rules_passed"],
                ["included_in_fare"],
                ["loyalty_complimentary"],
                ["no_inventory"],
            ],
        }
    )


@pytest.mark.parametrize("reason", sorted(NOT_CHARGEABLE_BOOKINGS))
def test_current_pricing_gets_no_credit_when_rules_make_the_item_free(reason):
    out = recommend(NOT_CHARGEABLE_BOOKINGS[reason], persist=False)
    assert out["offered"] is False
    assert out["rule_reason_codes"] == [reason]
    # Current Pricing would still quote a price for the item ...
    assert out["current_price"] > 0
    # ... but nobody pays it, so it earns nothing, exactly like the New Model.
    assert out["p_buy_current"] == 0.0
    assert out["expected_revenue_current"] == 0.0
    assert out["p_buy_new"] == 0.0
    assert out["expected_revenue_new"] == 0.0


def test_chargeable_booking_still_credits_both_systems():
    out = recommend(FIXTURE_BOOKING, persist=False)
    assert out["offered"] is True
    assert out["expected_revenue_current"] > 0
    assert out["expected_revenue_new"] > 0


def test_summary_leaves_free_bookings_out_of_both_sides():
    mixed = _mixed_offers()
    chargeable_only = mixed[mixed["offered"]].reset_index(drop=True)
    stats = summarise(mixed)
    reference = summarise(chargeable_only)

    current_rev = (120.0 * 0.50 + 90.0 * 0.40) / 2
    new_rev = (100.0 * 0.70 + 110.0 * 0.30) / 2
    assert stats["current_revpp"] == pytest.approx(current_rev)
    assert stats["new_revpp"] == pytest.approx(new_rev)
    assert stats["current_conversion"] == pytest.approx((0.50 + 0.40) / 2)
    assert stats["new_conversion"] == pytest.approx((0.70 + 0.30) / 2)
    for key in (
        "current_revpp",
        "new_revpp",
        "current_conversion",
        "new_conversion",
        "current_price_paid",
        "new_price_paid",
        "revenue_impact",
        "conversion_impact_pp",
    ):
        assert stats[key] == pytest.approx(reference[key]), key

    # Had Current Pricing been credited on the three free rows it would read higher.
    credited_on_free = float((mixed["current_price"] * mixed["p_buy_current"]).mean())
    assert credited_on_free > 0
    assert stats["current_revpp"] != pytest.approx(credited_on_free)


def test_free_bookings_are_reported_as_a_count():
    stats = summarise(_mixed_offers())
    assert stats["n"] == 5
    assert stats["n_chargeable"] == 2
    assert stats["n_not_chargeable"] == 3
    assert stats["not_chargeable_counts"] == {
        "included_in_fare": 1,
        "loyalty_complimentary": 1,
        "no_inventory": 1,
        "other": 0,
    }
    view = results_view(_mixed_offers())
    assert "3 (1 included in the fare, 1 loyalty complimentary, 1 no inventory)" in view["summary_lines"][3]
    assert "2 chargeable bookings" in view["sentence"]


def test_three_table_rows_reconcile_by_definition():
    for frame in (_mixed_offers(), pd.read_parquet(SIMULATED)):
        stats = summarise(frame)
        assert stats["current_revpp"] == pytest.approx(
            stats["current_conversion"] * stats["current_price_paid"]
        )
        assert stats["new_revpp"] == pytest.approx(
            stats["new_conversion"] * stats["new_price_paid"]
        )
    assert METRIC_ROWS == (
        "Revenue per chargeable booking (USD)",
        "Purchase rate (%)",
        "Average price paid (USD)",
    )
    assert "purchase rate multiplied by the average price paid" in TEST_RESULTS_BASIS
    assert "left out of both columns" in TEST_RESULTS_BASIS


def test_rule_that_removes_the_price_never_looks_at_the_price():
    for product, fare, loyalty, cabin, remaining in itertools.product(
        PRODUCTS, FARE_TYPES, LOYALTY, CABINS, (0, 5)
    ):
        booking = dict(
            product_type=product,
            fare_type=fare,
            loyalty=loyalty,
            cabin=cabin,
            remaining_extra_legroom=remaining,
        )
        reason = not_chargeable_reason(**booking)
        for price in (60.0, 140.0, 260.0):
            result = apply_business_rules(
                recommended_price=price, channel="web", route="SIN-LHR", **booking
            )
            assert result.offered is (reason is None)
            if reason is None:
                assert result.customer_price > 0
            else:
                assert result.reason_codes == [reason]
                assert reason in NOT_CHARGEABLE_REASONS
                expected = None if reason in UNAVAILABLE_REASONS else 0.0
                assert result.customer_price == expected


def test_simulated_bookings_credit_neither_system_on_free_items():
    offers = pd.read_parquet(SIMULATED)
    chargeable = chargeable_mask(offers)
    free = offers[~chargeable]
    priced = offers[chargeable]
    assert len(free) > 0 and len(priced) > 0
    assert len(free) + len(priced) == len(offers)

    assert (free["p_buy_current"] == 0).all()
    assert (free["expected_revenue_current"] == 0).all()
    assert (free["p_buy_new"] == 0).all()
    assert (free["expected_revenue_new"] == 0).all()
    assert (free["served_price"].fillna(0) == 0).all()
    assert (free["realised_purchase"] == 0).all()
    assert set(free["arm"]) == {"not_chargeable"}

    assert (priced["served_price"] > 0).all()
    assert "not_chargeable" not in set(priced["arm"])
    live = priced[priced["arm"] == "new_model"]
    assert (live["served_price"] == live["customer_price"]).all()
    others = priced[priced["arm"] != "new_model"]
    assert (others["served_price"] == others["current_price"]).all()

    stats = summarise(offers)
    assert stats["n_chargeable"] == len(priced)
    assert sum(stats["not_chargeable_counts"].values()) == len(free)
    for reason in FREE_REASONS | UNAVAILABLE_REASONS:
        assert reason in stats["not_chargeable_counts"]
