from __future__ import annotations

from typing import Any, Mapping

from business_rules import TemporaryCap
from new_model.recommend import recommend
from rollout import RolloutConfig, assign_new_model, is_shadow

NOT_CHARGEABLE_ARM = "not_chargeable"


def serve_booking(
    booking: Mapping[str, Any],
    cfg: RolloutConfig,
    temporary_caps: list[TemporaryCap] | None = None,
) -> dict[str, Any]:
    result = recommend(
        booking,
        allowed_min=cfg.allowed_min,
        allowed_max=cfg.allowed_max,
        temporary_caps=temporary_caps,
        persist=False,
    )
    use_new = assign_new_model(str(booking.get("booking_id", "anon")), cfg)
    shadow = is_shadow(cfg)

    if not result["offered"]:
        # Free or unavailable under Business Rules. Neither system charges for
        # it, so the booking is outside the price test in every rollout state.
        customer = result["customer_price"]  # 0.0 when free, None when unavailable
        arm = NOT_CHARGEABLE_ARM
    elif shadow:
        customer = result["current_price"]
        arm = "current_shadow"
    elif use_new:
        customer = result["customer_price"]
        arm = "new_model"
    else:
        customer = result["current_price"]
        arm = "current_pricing"

    out = dict(result)
    out["served_price"] = customer
    out["arm"] = arm
    out["shadow"] = shadow
    out["traffic_percent"] = cfg.traffic_percent
    return out
