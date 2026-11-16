import pandas as pd
import pytest

from lab.paths import STATE_DIR
from monitor.health import (
    EXPAND_REVENUE,
    MIN_LIVE_BOOKINGS,
    behaviour_changed,
    drift_gap,
    health,
)
from monitor.test_results import comparison_sentence, summarise


def _frame():
    return pd.DataFrame(
        {
            "route": ["SIN-LHR", "SIN-BOM", "SIN-BOM"],
            "days_to_departure": [4, 3, 2],
            "current_price": [120.0, 90.0, 95.0],
            "new_model_recommended_price": [145.0, 110.0, 120.0],
            "customer_price": [145.0, 110.0, 120.0],
            "p_buy_current": [0.27, 0.30, 0.28],
            "p_buy_new": [0.24, 0.40, 0.42],
            "p_buy_at_recommendation": [0.24, 0.40, 0.42],
            "arm": ["new_model", "new_model", "new_model"],
            "offered": [True, True, True],
            "rule_reason_codes": [["rules_passed"], ["rules_passed"], ["rules_passed"]],
            "fallback_layer": ["new_model", "new_model", "new_model"],
            "realised_purchase": [1, 0, 0],
            "served_price": [145.0, 110.0, 120.0],
        }
    )


def test_summarise_hand_calc():
    stats = summarise(_frame())
    current_rev = (120.0 * 0.27 + 90.0 * 0.30 + 95.0 * 0.28) / 3
    new_rev = (145.0 * 0.24 + 110.0 * 0.40 + 120.0 * 0.42) / 3
    current_conv = (0.27 + 0.30 + 0.28) / 3
    new_conv = (0.24 + 0.40 + 0.42) / 3
    assert stats["n"] == 3
    assert stats["business_rule_violations"] == 0
    assert stats["current_revpp"] == pytest.approx(current_rev)
    assert stats["new_revpp"] == pytest.approx(new_rev)
    assert stats["current_conversion"] == pytest.approx(current_conv)
    assert stats["new_conversion"] == pytest.approx(new_conv)
    assert stats["current_asp"] == pytest.approx((120.0 + 90.0 + 95.0) / 3)
    assert stats["new_asp"] == pytest.approx((145.0 + 110.0 + 120.0) / 3)
    assert stats["current_price_paid"] == pytest.approx(current_rev / current_conv)
    assert stats["new_price_paid"] == pytest.approx(new_rev / new_conv)
    assert stats["n_chargeable"] == 3
    assert stats["n_not_chargeable"] == 0
    assert stats["revenue_impact"] == pytest.approx(new_rev / current_rev - 1.0)
    assert stats["conversion_impact_pp"] == pytest.approx((new_conv - current_conv) * 100)


def test_health_hold_on_sin_bom_drift():
    report = health(_frame())
    assert report["model_health"]["drift_gap"] > 0.08
    assert report["decision"] == "HOLD"
    assert "SIN" in report["reason"] and "BOM" in report["reason"]
    assert "seven days" in report["reason"]
    assert report["model_health"]["customer_behaviour_changed"]["state"] == "warn"


def test_hold_reason_requires_computed_drift():
    frame = _frame()
    frame["realised_purchase"] = [1, 1, 1]
    report = health(frame)
    assert report["model_health"]["drift_gap"] <= 0.08
    assert "behaving differently" not in report["reason"]


def test_pricing_failure_and_fallback_thresholds():
    ok = health(_frame(), fallback_rate=0.0)
    assert ok["system_health"]["pricing_failures"]["state"] == "pass"
    assert ok["system_health"]["fallback_usage"]["state"] == "pass"
    bad = health(_frame(), fallback_rate=0.05)
    assert bad["system_health"]["pricing_failures"]["state"] == "fail"
    assert bad["system_health"]["fallback_usage"]["state"] == "fail"


def test_summarise_counts_business_rule_violations():
    frame = _frame()
    frame.loc[0, "rule_reason_codes"] = ["included_in_fare"]
    frame.loc[0, "customer_price"] = 80.0
    frame.loc[0, "offered"] = True
    stats = summarise(frame)
    assert stats["business_rule_violations"] == 1


def test_impact_sentence_uses_computed_stats():
    stats = summarise(_frame())
    sentence = comparison_sentence(stats)
    assert "in the simulation" in sentence
    assert "8.0%" not in sentence
    assert f"{abs(stats['revenue_impact']):.1%}" in sentence


def _favourable(n_live: int, n_shadow: int = 0) -> pd.DataFrame:
    """Chargeable bookings away from the drift segment where the New Model earns more."""
    rows = n_live + n_shadow
    return pd.DataFrame(
        {
            "route": ["SIN-LHR"] * rows,
            "days_to_departure": [20] * rows,
            "current_price": [150.0] * rows,
            "customer_price": [130.0] * rows,
            "p_buy_current": [0.50] * rows,
            "p_buy_new": [0.80] * rows,
            "arm": ["new_model"] * n_live + ["current_shadow"] * n_shadow,
            "offered": [True] * rows,
            "rule_reason_codes": [["rules_passed"]] * rows,
            "fallback_layer": ["new_model"] * rows,
            # Four in five live bookings buy, as predicted; one in two shadow bookings.
            "realised_purchase": [1 if i % 5 else 0 for i in range(n_live)]
            + [i % 2 for i in range(n_shadow)],
            "served_price": [130.0] * n_live + [150.0] * n_shadow,
        }
    )


def test_expand_needs_a_minimum_number_of_live_bookings():
    small = health(_favourable(n_live=7, n_shadow=215))
    assert small["stats"]["revenue_impact"] > EXPAND_REVENUE
    assert small["commercial"]["revenue"]["state"] == "pass"
    assert small["decision"] == "HOLD"
    assert "only 7 bookings have been served its price" in small["reason"]
    assert f"At least {MIN_LIVE_BOOKINGS} are needed before expanding" in small["reason"]
    assert small["live_sample"] == {"value": 7, "minimum": MIN_LIVE_BOOKINGS, "state": "warn"}

    just_short = health(_favourable(n_live=MIN_LIVE_BOOKINGS - 1))
    assert just_short["decision"] == "HOLD"

    shadow_only = health(_favourable(n_live=0, n_shadow=300))
    assert shadow_only["decision"] == "HOLD"
    assert "no bookings have been served its price" in shadow_only["reason"]

    enough = health(_favourable(n_live=MIN_LIVE_BOOKINGS))
    assert enough["decision"] == "Expand"
    assert enough["live_sample"]["state"] == "pass"


def test_return_to_current_pricing_does_not_wait_for_live_bookings():
    frame = _favourable(n_live=7, n_shadow=215)
    frame["p_buy_new"] = 0.30  # USD 130 x 0.30 = 39 against USD 150 x 0.50 = 75
    report = health(frame)
    assert report["commercial"]["revenue"]["state"] == "fail"
    assert report["decision"] == "Return to Current Pricing"


def test_predictions_are_not_judged_on_a_handful_of_live_bookings():
    small = health(_favourable(n_live=7, n_shadow=215))
    assert small["model_health"]["predictions_accurate"] == {"state": "warn", "judged": False}

    enough = health(_favourable(n_live=MIN_LIVE_BOOKINGS))
    assert enough["model_health"]["predictions_accurate"] == {"state": "pass", "judged": True}

    nobody_bought = _favourable(n_live=MIN_LIVE_BOOKINGS)
    nobody_bought["realised_purchase"] = 0
    report = health(nobody_bought)
    assert report["model_health"]["predictions_accurate"] == {"state": "fail", "judged": True}


def test_drift_is_read_on_chargeable_bookings_at_the_price_served():
    # Shadow bookings on the drift segment saw the Current Pricing price, so the
    # prediction that counts is the purchase chance at that price.
    shadow = pd.DataFrame(
        {
            "route": ["SIN-BOM"] * 4,
            "days_to_departure": [3] * 4,
            "current_price": [100.0] * 4,
            "customer_price": [70.0] * 4,
            "p_buy_current": [0.50] * 4,
            "p_buy_new": [0.90] * 4,
            "arm": ["current_shadow"] * 4,
            "offered": [True] * 4,
            "rule_reason_codes": [["rules_passed"]] * 4,
            "realised_purchase": [1, 0, 1, 0],
            "served_price": [100.0] * 4,
        }
    )
    assert drift_gap(shadow) == pytest.approx(0.0)
    assert behaviour_changed(shadow) is False

    # The same bookings in the live arm: now the New Model price was served.
    live = shadow.assign(arm="new_model", served_price=70.0)
    assert drift_gap(live) == pytest.approx(0.40)
    assert behaviour_changed(live) is True

    # Free bookings on the segment have no purchase at a price and must not dilute the gap.
    free = live.assign(
        offered=False,
        customer_price=0.0,
        p_buy_current=0.0,
        p_buy_new=0.0,
        realised_purchase=0,
        served_price=0.0,
        rule_reason_codes=[["included_in_fare"]] * 4,
    )
    assert drift_gap(pd.concat([live, free], ignore_index=True)) == pytest.approx(0.40)


def test_simulated_run_does_not_expand_on_a_small_live_arm():
    report = health(pd.read_parquet(STATE_DIR / "simulated_offers.parquet"))
    live = report["stats"]["n_new_model_live"]
    assert report["live_sample"]["value"] == live
    if live < MIN_LIVE_BOOKINGS:
        assert report["decision"] != "Expand"
        assert report["model_health"]["predictions_accurate"]["judged"] is False
