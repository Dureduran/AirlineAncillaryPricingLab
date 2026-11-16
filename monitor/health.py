from __future__ import annotations

import pandas as pd

from monitor.test_results import chargeable_mask, summarise

DRIFT_ROUTE = "SIN-BOM"
DRIFT_DTD = 7
DRIFT_GAP_THRESHOLD = 0.08
FAILURE_RATE_THRESHOLD = 0.02
FALLBACK_RATE_THRESHOLD = 0.03
CALIBRATION_GAP_THRESHOLD = 0.12
REVENUE_FLOOR = -0.02
CONVERSION_FLOOR_PP = -3.0
EXPAND_REVENUE = 0.04
# Fewest bookings that must have been served the New Model price before the
# monitor reads the live arm. At 100 bookings a purchase rate is known to within
# about +/-10 percentage points at 95% confidence (1.96 x sqrt(0.25 / 100)); below
# that the live arm is noise. This is a floor, not a power calculation.
MIN_LIVE_BOOKINGS = 100

HOLD_DRIFT_REASON = (
    "SIN–BOM bookings within seven days of departure are behaving differently "
    "from the training data. Keep the New Model at 20% of traffic while investigating."
)


def hold_small_sample_reason(n_live: int, minimum: int = MIN_LIVE_BOOKINGS) -> str:
    if n_live == 0:
        served = "no bookings have been"
    elif n_live == 1:
        served = "only 1 booking has been"
    else:
        served = f"only {n_live:,} bookings have been"
    return (
        f"The simulated comparison favours the New Model, but {served} served its price. "
        f"At least {minimum:,} are needed before expanding. "
        "Keep the current traffic split and continue monitoring."
    )


def _flag(ok: bool, warn: bool = False) -> str:
    if ok and not warn:
        return "pass"
    if warn:
        return "warn"
    return "fail"


def drift_gap(offers: pd.DataFrame) -> float:
    """Predicted minus realised purchase rate on the drift segment.

    Read on chargeable bookings only, at the price each customer was served:
    the New Model price in the live arm, the Current Pricing price otherwise.
    """
    if "route" not in offers.columns or "days_to_departure" not in offers.columns:
        return 0.0
    priced = offers[chargeable_mask(offers)]
    drift = priced[(priced["route"] == DRIFT_ROUTE) & (priced["days_to_departure"] <= DRIFT_DTD)]
    if not len(drift) or "p_buy_new" not in drift.columns:
        return 0.0
    predicted_at_served = drift["p_buy_new"]
    if "arm" in drift.columns and "p_buy_current" in drift.columns:
        predicted_at_served = drift["p_buy_new"].where(
            drift["arm"] == "new_model", drift["p_buy_current"]
        )
    predicted = float(predicted_at_served.mean())
    realised = (
        float(drift["realised_purchase"].mean())
        if "realised_purchase" in drift.columns
        else predicted
    )
    return predicted - realised


def behaviour_changed(offers: pd.DataFrame) -> bool:
    return drift_gap(offers) > DRIFT_GAP_THRESHOLD


def failure_rate(offers: pd.DataFrame) -> float:
    if offers.empty:
        return 0.0
    if "fallback_layer" not in offers.columns:
        return 0.0
    return float((offers["fallback_layer"] != "new_model").mean())


def health(offers: pd.DataFrame, fallback_rate: float | None = None) -> dict:
    stats = summarise(offers)
    fail_rate = failure_rate(offers) if fallback_rate is None else float(fallback_rate)
    gap = drift_gap(offers)
    drifted = gap > DRIFT_GAP_THRESHOLD

    n_live = int(stats["n_new_model_live"])
    enough_live = n_live >= MIN_LIVE_BOOKINGS
    # Predicted against realised on the same live bookings. Not judged at all
    # while the live arm is below the minimum.
    calibration_ok = (
        abs(stats["live_predicted_conversion"] - stats["live_conversion"])
        < CALIBRATION_GAP_THRESHOLD
    )
    rev_ok = stats["revenue_impact"] > REVENUE_FLOOR
    conv_ok = stats["conversion_impact_pp"] > CONVERSION_FLOOR_PP
    fail_ok = fail_rate < FAILURE_RATE_THRESHOLD
    fallback_ok = fail_rate < FALLBACK_RATE_THRESHOLD
    rules_ok = stats["business_rule_violations"] == 0

    if drifted:
        decision = "HOLD"
        reason = HOLD_DRIFT_REASON
    elif not rev_ok or not conv_ok:
        # A safety stop does not wait for a live sample.
        decision = "Return to Current Pricing"
        reason = "Commercial performance is outside the agreed tolerance."
    elif stats["revenue_impact"] > EXPAND_REVENUE and conv_ok:
        if enough_live:
            decision = "Expand"
            reason = "Revenue is up and conversion is within tolerance. Consider moving from 20% to 50%."
        else:
            decision = "HOLD"
            reason = hold_small_sample_reason(n_live)
    else:
        decision = "HOLD"
        reason = "Keep the current traffic split and continue monitoring."

    return {
        "commercial": {
            "revenue": {"value": stats["revenue_impact"], "state": _flag(rev_ok)},
            "conversion": {"value": stats["conversion_impact_pp"], "state": _flag(conv_ok)},
        },
        "model_health": {
            "predictions_accurate": {
                "state": _flag(calibration_ok, warn=not enough_live),
                "judged": enough_live,
            },
            "customer_behaviour_changed": {"state": _flag(not drifted, warn=drifted)},
            "drift_gap": gap,
        },
        "system_health": {
            "pricing_failures": {"value": fail_rate, "state": _flag(fail_ok)},
            "fallback_usage": {"value": fail_rate, "state": _flag(fallback_ok)},
        },
        "business_rules": {
            "violations": {"value": stats["business_rule_violations"], "state": _flag(rules_ok)},
        },
        "live_sample": {
            "value": n_live,
            "minimum": MIN_LIVE_BOOKINGS,
            "state": _flag(enough_live, warn=not enough_live),
        },
        "decision": decision,
        "reason": reason,
        "stats": stats,
        "behaviour_changed": drifted,
    }
