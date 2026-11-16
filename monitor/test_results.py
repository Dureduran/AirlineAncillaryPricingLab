from __future__ import annotations

from typing import Any

import pandas as pd

from business_rules import FREE_REASONS, NOT_CHARGEABLE_REASONS

SHOULD_BE_FREE = FREE_REASONS

# How the bookings left out of the comparison are named when they are counted.
NOT_CHARGEABLE_LABELS = {
    "included_in_fare": "included in the fare",
    "loyalty_complimentary": "loyalty complimentary",
    "no_inventory": "no inventory",
}


def _codes(val: Any) -> list[str]:
    if val is None:
        return []
    try:
        if pd.isna(val):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(val, str):
        text = val.strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].replace("'", "").replace('"', "")
            return [part.strip() for part in inner.split(",") if part.strip()]
        return [text] if text else []
    if isinstance(val, (list, tuple, set)):
        return [str(item) for item in val]
    if hasattr(val, "tolist"):
        return [str(item) for item in val.tolist()]
    try:
        return [str(item) for item in list(val)]
    except TypeError:
        return [str(val)]


def count_business_rule_violations(offers: pd.DataFrame) -> int:
    if offers.empty or "rule_reason_codes" not in offers.columns:
        return 0
    count = 0
    for _, row in offers.iterrows():
        codes = _codes(row.get("rule_reason_codes"))
        offered = bool(row.get("offered", False))
        try:
            price = row.get("customer_price")
            price_f = float(price) if price is not None and not pd.isna(price) else 0.0
        except (TypeError, ValueError):
            price_f = 0.0
        if offered and price_f > 0 and any(code in SHOULD_BE_FREE for code in codes):
            count += 1
    return count


def chargeable_mask(offers: pd.DataFrame) -> pd.Series:
    """True where Business Rules leave a price to charge.

    An item that is included in the fare, complimentary or out of inventory is
    free or unavailable whichever system quoted it. Those bookings are left out
    of both sides of every comparison and reported as a count instead.
    """
    mask = pd.Series(True, index=offers.index, dtype=bool)
    if "offered" in offers.columns:
        mask &= offers["offered"].fillna(False).astype(bool)
    if "rule_reason_codes" in offers.columns:
        blocked = offers["rule_reason_codes"].apply(
            lambda val: any(code in NOT_CHARGEABLE_REASONS for code in _codes(val))
        )
        mask &= ~blocked.astype(bool)
    return mask


def not_chargeable_counts(offers: pd.DataFrame, mask: pd.Series | None = None) -> dict[str, int]:
    """Count the bookings left out of the comparison, by Business Rules reason."""
    if mask is None:
        mask = chargeable_mask(offers)
    counts = {code: 0 for code in NOT_CHARGEABLE_LABELS}
    counts["other"] = 0
    left_out = offers[~mask]
    if "rule_reason_codes" not in left_out.columns:
        counts["other"] = int(len(left_out))
        return counts
    for val in left_out["rule_reason_codes"]:
        reason = next((code for code in _codes(val) if code in NOT_CHARGEABLE_LABELS), "other")
        counts[reason] += 1
    return counts


def not_chargeable_phrase(stats: dict[str, Any]) -> str:
    """For example: 278 (231 included in the fare, 36 loyalty complimentary, 11 no inventory)."""
    counts = stats.get("not_chargeable_counts", {})
    parts = [
        f"{counts[code]:,} {label}"
        for code, label in NOT_CHARGEABLE_LABELS.items()
        if counts.get(code)
    ]
    if counts.get("other"):
        parts.append(f"{counts['other']:,} other")
    total = f"{int(stats.get('n_not_chargeable', 0)):,}"
    return f"{total} ({', '.join(parts)})" if parts else total


def comparison_sentence(stats: dict[str, Any]) -> str:
    rev = float(stats["revenue_impact"])
    conv = float(stats["conversion_impact_pp"])
    direction = "increases" if rev >= 0 else "decreases"
    basis = ""
    if "n_chargeable" in stats:
        basis = f"On the {int(stats['n_chargeable']):,} chargeable bookings, "
    return (
        f"{basis}the New Model {direction} expected revenue by {abs(rev):.1%} in the simulation "
        f"while conversion moves {conv:+.1f} percentage points versus Current Pricing."
    )


impact_sentence = comparison_sentence


def summary_lines(stats: dict[str, Any]) -> list[str]:
    lines = [
        f"Revenue impact: {stats['revenue_impact']:+.1%}",
        f"Conversion impact: {stats['conversion_impact_pp']:+.1f} percentage points",
        f"Business-rule violations: {stats['business_rule_violations']}",
    ]
    if "n_not_chargeable" in stats:
        lines.append(f"Left out of both sides, free or unavailable: {not_chargeable_phrase(stats)}")
    return lines


def _mean(series: pd.Series) -> float:
    return float(series.mean()) if len(series) else 0.0


def summarise(offers: pd.DataFrame) -> dict:
    """Compare Current Pricing and the New Model on the same bookings.

    Only chargeable bookings enter either side (see chargeable_mask). For each
    system, revenue per chargeable booking is the average of price x purchase
    chance, the purchase rate is the average purchase chance, and the average
    price paid is revenue divided by the purchase rate. So revenue equals
    purchase rate x average price paid by definition.
    """
    mask = chargeable_mask(offers)
    priced = offers[mask]

    current_rev = _mean(priced["current_price"] * priced["p_buy_current"])
    current_conv = _mean(priced["p_buy_current"])
    current_quoted = _mean(priced["current_price"])
    current_paid = current_rev / current_conv if current_conv else 0.0

    new_price = priced["customer_price"].fillna(0)
    new_exp_rev = _mean(new_price * priced["p_buy_new"])
    new_exp_conv = _mean(priced["p_buy_new"])
    new_quoted = _mean(new_price)
    new_paid = new_exp_rev / new_exp_conv if new_exp_conv else 0.0

    if "arm" in priced.columns:
        live = priced[priced["arm"] == "new_model"]
    else:
        live = priced.iloc[0:0]
    n_live = int(len(live))

    if n_live and "served_price" in live.columns and "realised_purchase" in live.columns:
        live_rev = float((live["served_price"].fillna(0) * live["realised_purchase"]).mean())
        live_conv = float(live["realised_purchase"].mean())
        live_asp = float(live["served_price"].mean())
        # Prediction for the same live bookings, at the price they were served.
        live_predicted_conv = float(live["p_buy_new"].mean())
    else:
        live_rev = new_exp_rev
        live_conv = new_exp_conv
        live_asp = new_quoted
        live_predicted_conv = new_exp_conv

    rev_impact = (new_exp_rev / current_rev - 1.0) if current_rev else 0.0
    conv_impact_pp = (new_exp_conv - current_conv) * 100
    counts = not_chargeable_counts(offers, mask)

    return {
        "current_revpp": current_rev,
        "new_revpp": new_exp_rev,
        "current_conversion": current_conv,
        "new_conversion": new_exp_conv,
        "current_price_paid": float(current_paid),
        "new_price_paid": float(new_paid),
        "current_asp": current_quoted,
        "new_asp": new_quoted,
        "revenue_impact": float(rev_impact),
        "conversion_impact_pp": float(conv_impact_pp),
        "business_rule_violations": count_business_rule_violations(offers),
        "n": int(len(offers)),
        "n_chargeable": int(len(priced)),
        "n_not_chargeable": int(len(offers) - len(priced)),
        "not_chargeable_counts": counts,
        "n_new_model_live": n_live,
        "live_revpp": live_rev,
        "live_conversion": live_conv,
        "live_predicted_conversion": live_predicted_conv,
        "live_asp": live_asp,
    }


__all__ = [
    "NOT_CHARGEABLE_LABELS",
    "SHOULD_BE_FREE",
    "chargeable_mask",
    "comparison_sentence",
    "count_business_rule_violations",
    "impact_sentence",
    "not_chargeable_counts",
    "not_chargeable_phrase",
    "summarise",
    "summary_lines",
]
