from __future__ import annotations

from typing import Any

import pandas as pd

from app.ui import money, pct
from lab.copy import CURRENT_PRICING, NEW_MODEL
from monitor.test_results import comparison_sentence, not_chargeable_phrase, summarise

METRIC_ROWS = (
    "Revenue per chargeable booking (USD)",
    "Purchase rate (%)",
    "Average price paid (USD)",
)

# Shown under the table so the reader knows which bookings are compared and how.
TEST_RESULTS_BASIS = (
    "How to read the table: both columns cover the same bookings, the ones where a price "
    "is actually charged. A booking whose item is included in the fare, complimentary for "
    "the loyalty tier or out of inventory is free or unavailable whichever system prices "
    "it, so it is left out of both columns and counted below. The figures are expected "
    "values, using the New Model's estimated purchase chance at each price: Current Pricing "
    "at its own quote, the New Model at its price after Business Rules. Revenue per "
    "chargeable booking is the purchase rate multiplied by the average price paid."
)


def results_table(stats: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            CURRENT_PRICING: [
                money(stats["current_revpp"]),
                pct(stats["current_conversion"]),
                money(stats["current_price_paid"]),
            ],
            NEW_MODEL: [
                money(stats["new_revpp"]),
                pct(stats["new_conversion"]),
                money(stats["new_price_paid"]),
            ],
        },
        index=list(METRIC_ROWS),
    )


def formatted_summary_lines(stats: dict[str, Any]) -> list[str]:
    return [
        f"**Revenue impact:** {stats['revenue_impact']:+.1%}",
        f"**Conversion impact:** {stats['conversion_impact_pp']:+.1f} percentage points",
        f"**Business-rule violations:** {stats['business_rule_violations']}",
        f"**Left out of both columns, free or unavailable:** {not_chargeable_phrase(stats)}",
    ]


def results_view(offers: pd.DataFrame) -> dict[str, Any]:
    stats = summarise(offers)
    return {
        "stats": stats,
        "table": results_table(stats),
        "sentence": comparison_sentence(stats),
        "summary_lines": formatted_summary_lines(stats),
    }
