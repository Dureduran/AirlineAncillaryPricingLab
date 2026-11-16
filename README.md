# Ancillary Pricing Production Lab

Testing, safely rolling out and monitoring machine-learning pricing for airline seats and baggage

Independent portfolio prototype using synthetic and public data. No airline internal data, systems or proprietary pricing logic are used. This lab is not affiliated with any carrier.

## What this is

Most airlines already have an in-house ancillary dynamic-pricing capability. This lab is not another dashboard that only predicts a price. It shows how a revenue-management lead would evaluate a **New Model** against **Current Pricing**, apply **Business Rules** as the final control, introduce the model in a traffic ladder (shadow → 5% → 20% → 50% → 100%), measure commercial impact, and **Return to Current Pricing** if it is not healthy.

**v1 products:** extra baggage and preferred / extra-legroom seat only. Fare-brand upgrades (Basic → Value / Comfort) are a future expansion, not built here.

Public GitHub: [Dureduran/AirlineAncillaryPricingLab](https://github.com/Dureduran/AirlineAncillaryPricingLab)

Live lab: [https://dureduran.github.io/AirlineAncillaryPricingLab/index.html](https://dureduran.github.io/AirlineAncillaryPricingLab/index.html)

Executive walkthrough: [docs/walkthrough.html](https://dureduran.github.io/AirlineAncillaryPricingLab/walkthrough.html)

One-page brief: [docs/brief.html](https://dureduran.github.io/AirlineAncillaryPricingLab/brief.html) ([PDF](https://github.com/Dureduran/AirlineAncillaryPricingLab/blob/main/docs/one_page_brief.pdf))

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m data.build_offer_log
python -m new_model.train
pytest
streamlit run app/Home.py
```

Open the app and walk **Price Explanation → Pricing Controls → Pricing Test Results → Production Monitor**. Every screen carries: Simulated result using synthetic/public data.

## Architecture

**Online path**

Booking information → possible prices → New Model → P(buy) at each price → choose max expected revenue → Business Rules → final price → customer buys / does not buy → save result → monitor.

**Offline path (Databricks Free)**

Historical results → train New Model → test against Current Pricing → small controlled rollout → measure revenue + conversion → expand / pause / return.

See [databricks/README_DATABRICKS.md](databricks/README_DATABRICKS.md).

**Offline path (Google Cloud — Colab + BigQuery)**

Same offer log → ingest training columns into BigQuery `ancillary_lab` → train New Model in Colab or Vertex AI Workbench → export `new_model/model.joblib` → the Streamlit lab scores that artifact. Paid Vertex Prediction is not required.

See [gcp/README_GCP.md](gcp/README_GCP.md) and the Colab notebook [gcp/run_ingest_and_train.ipynb](gcp/run_ingest_and_train.ipynb).

## How the test compares the two systems

Pricing Test Results compares Current Pricing and the New Model on the same bookings: the ones where a price is actually charged. A booking whose item is included in the fare, complimentary for the loyalty tier or out of inventory is free or unavailable whichever system prices it, so it is left out of both sides and reported as a count. Revenue per chargeable booking is the purchase rate multiplied by the average price paid. The figures are expected values from the New Model's own purchase estimates, not observed sales.

The Production Monitor does not expand on a small live arm. Expand needs at least 100 bookings served the New Model price; below that a favourable comparison gives a Rollout Decision of HOLD. Return to Current Pricing does not wait for a live sample.

Current simulated run: 500 bookings, 222 chargeable. Left out of both sides, free or unavailable: 278 (231 included in the fare, 36 loyalty complimentary, 11 no inventory). Revenue per chargeable booking is USD 94.20 for Current Pricing and USD 102.91 for the New Model (+9.2%). All of the gain comes from extra baggage, which is still in shadow on every route. 7 bookings were served the New Model price, so the Rollout Decision is HOLD.

Corrected 16 November 2026. Until then the lab reported −44.3% revenue and a decision to Return to Current Pricing. That comparison was not like-for-like: it applied Business Rules to the New Model only, so on the 278 free or unavailable bookings the New Model counted as USD 0 while Current Pricing was still credited with its quote.

## Language

User-facing copy uses Current Pricing, New Model, Business Rules, Rollout Decision, Return to Current Pricing, and Pricing Test Results.

## Checkout fallback

1. New Model  
2. Current Pricing  
3. Simple pricing rules  
4. Safe fixed price  

If the pricing model fails during checkout, the customer still gets a valid price.

## Disclaimer

Fare-brand inclusion, loyalty complimentary seats, and online-versus-airport baggage differences in this repo are **portfolio stand-ins** shaped by public airline merchandising patterns. They are not a live carrier's production logic.
