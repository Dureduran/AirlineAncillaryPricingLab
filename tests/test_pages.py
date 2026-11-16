from pathlib import Path

import pandas as pd
import pytest

from app.pricing_test_results import METRIC_ROWS, TEST_RESULTS_BASIS, results_view
from app.ui import money, pct
from lab.copy import DISCLAIMER, SIMULATED_BANNER
from lab.paths import STATE_DIR
from monitor.health import MIN_LIVE_BOOKINGS, health
from monitor.test_results import chargeable_mask, not_chargeable_phrase

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INDEX = DOCS / "index.html"
WALKTHROUGH = DOCS / "walkthrough.html"
BRIEF = DOCS / "brief.html"
README = ROOT / "README.md"
SIMULATED = STATE_DIR / "simulated_offers.parquet"

CORRECTION = "Corrected 16 November 2026"
# Figures the pages carried before the comparison was made like-for-like.
SUPERSEDED = ("USD 82.05", "USD 45.69", "USD 141.62", "USD 54.09", "57.5%", "37.8%")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _signed(text: str) -> str:
    """The pages write negative numbers with a true minus sign."""
    return text.replace("-", "−")


@pytest.fixture(scope="module")
def offers() -> pd.DataFrame:
    return pd.read_parquet(SIMULATED)


@pytest.fixture(scope="module")
def stats(offers) -> dict:
    return results_view(offers)["stats"]


@pytest.fixture(scope="module")
def report(offers) -> dict:
    return health(offers)


def test_github_pages_includes_walkthrough():
    index = _read(INDEX)
    assert WALKTHROUGH.is_file()
    assert 'href="walkthrough.html"' in index
    text = _read(WALKTHROUGH)
    assert "EXECUTIVE WALKTHROUGH" in text
    assert "Return to Current Pricing" in text


def test_published_table_matches_the_simulated_bookings(stats):
    figures = [
        money(stats["current_revpp"]),
        money(stats["new_revpp"]),
        pct(stats["current_conversion"]),
        pct(stats["new_conversion"]),
        money(stats["current_price_paid"]),
        money(stats["new_price_paid"]),
        _signed(f"{stats['revenue_impact']:+.1%}"),
        _signed(f"{stats['conversion_impact_pp']:+.1f}"),
    ]
    for page in (INDEX, WALKTHROUGH):
        text = _read(page)
        for figure in figures:
            assert figure in text, f"{page.name} does not show {figure}"
        assert f"{stats['n_chargeable']} chargeable" in text
        for old in SUPERSEDED:
            assert old not in text, f"{page.name} still shows {old}"

    index = _read(INDEX)
    for row in METRIC_ROWS:
        assert f"<td>{row}</td>" in index
    assert f"n={stats['n_chargeable']} chargeable bookings out of {stats['n']} simulated" in index
    assert f"Live New Model arm n={stats['n_new_model_live']}" in index
    assert not_chargeable_phrase(stats) in index
    assert not_chargeable_phrase(stats) in _read(README)


def test_index_explains_the_same_basis_as_the_app():
    label, basis = TEST_RESULTS_BASIS.split(": ", 1)
    index = _read(INDEX)
    assert f"<b>{label}:</b> {basis}" in index


def test_published_decision_matches_the_monitor(report):
    stats = report["stats"]
    index = _read(INDEX)
    decision_box = index.split('<div class="decision-label">ROLLOUT DECISION</div>')[1].split("</div>")[0]
    assert f">{report['decision']}</h2>" in decision_box
    assert report["reason"] in decision_box

    live = report["live_sample"]
    assert f"{live['value']} of {live['minimum']} needed" in index
    assert live["minimum"] == MIN_LIVE_BOOKINGS

    walkthrough = _read(WALKTHROUGH)
    assert f'<span class="tag hold">{report["decision"]}</span>' in walkthrough
    assert f"only {stats['n_new_model_live']} bookings have been served its price" in walkthrough
    assert f"At least {MIN_LIVE_BOOKINGS} are needed before expanding" in walkthrough
    # The old conclusion must not come back as the walkthrough's answer.
    assert "Do not leave the New Model live" not in walkthrough
    assert "loses 44%" not in walkthrough


def test_pages_split_the_result_by_product(offers):
    priced = offers[chargeable_mask(offers)]
    index = _read(INDEX)
    walkthrough = _read(WALKTHROUGH)
    for product in ("extra_baggage", "extra_legroom"):
        rows = priced[priced["product_type"] == product]
        current = float((rows["current_price"] * rows["p_buy_current"]).mean())
        new = float((rows["customer_price"] * rows["p_buy_new"]).mean())
        figure = f"{_signed(f'{new / current - 1:+.1%}')}, n={len(rows)})"
        if product == "extra_legroom":
            figure = f"{_signed(f'{new / current - 1:+.1%}')} (n={len(rows)})"
        assert figure in index, f"index.html does not show {figure}"
        assert figure in walkthrough, f"walkthrough.html does not show {figure}"


def test_earlier_result_stays_visible_only_as_a_dated_correction():
    for page in (INDEX, WALKTHROUGH, README):
        text = _read(page)
        assert CORRECTION in text, f"{page.name} has no correction note"
        assert "not like-for-like" in text
        # −44.3% appears only where the page says what it used to report.
        for chunk in text.split("−44.3%")[:-1]:
            assert "Until then" in chunk[-160:] or "until 16 November 2026" in chunk[-160:], page.name


def test_every_page_still_says_the_result_is_simulated():
    assert SIMULATED_BANNER in _read(INDEX)
    assert DISCLAIMER in _read(INDEX)
    assert "Simulated result using synthetic/public data" in _read(WALKTHROUGH)
    assert "Results are simulated using synthetic and public data" in _read(BRIEF)
    assert DISCLAIMER in _read(README)
