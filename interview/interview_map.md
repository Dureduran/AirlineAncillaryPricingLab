# Interview story map

Independent portfolio prototype using synthetic and public data.

| Story they want | Screen / artefact |
|---|---|
| Inherit existing pricing and improve it in-house | Opening line + Price Explanation (Current Pricing vs New Model) |
| Business Rules have final control | Price Explanation cap line; Pricing Controls temporary cap |
| Safe rollout | Pricing Controls: shadow → 5% → 20% → 50% → 100% |
| Commercial impact | Pricing Test Results (revenue per chargeable booking, purchase rate, average price paid; both systems on the same bookings) |
| Monitor / HOLD | Production Monitor HOLD decision with a specific reason: fewer than 100 bookings served the New Model price, or a market/DTD drift |
| Checkout fallback | New Model → Current Pricing → simple rules → safe fixed price |
| Adoption / change | RM traffic and pause controls, not per-passenger approve |
| POC into production | Databricks notebooks + exported model + fallback |

Keep simulated-data honesty in every answer. Say: Simulated result using synthetic/public data.
