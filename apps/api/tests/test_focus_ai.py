"""AI model billing from FOCUS rows: tokens, cost and model identity from imported SkuPriceDetails.
All provider names, models, prices and quantities are SYNTHETIC."""

import csv
import io
import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import app, two_tenants

from cfa_tokenomics.focus import importer as imp
from cfa_tokenomics.focus.ai import ai_token_report

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
NOW = datetime(2026, 3, 1, tzinfo=UTC)
START, END = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
COLS = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory", "ChargeClass",
    "ChargePeriodStart", "ChargePeriodEnd", "BillingCurrency", "BillingAccountId", "ServiceName",
    "ServiceCategory", "ServiceProviderName", "ConsumedQuantity", "ConsumedUnit", "PricingQuantity",
    "PricingUnit", "SkuId", "SkuPriceId", "SkuMeter", "SkuPriceDetails",
]  # fmt: skip


def line(cost, tokens, *, props=None, day=1, model="model-a", provider="Provider One", cat="Usage",
         klass="", service_cat="AI and Machine Learning", unit="Tokens", cur="USD", meter="tokens",
         sku="sku-1", acct="ba1"):  # fmt: skip
    details = (
        {"ModelId": model, "ModelDeveloper": "Dev One", **(props or {})} if model else (props or {})
    )
    return [
        cost, cost, cost, cost, cat, klass, f"2026-01-{day:02d}T00:00:00Z", f"2026-01-{day:02d}T01:00:00Z",
        cur, acct, "Model Service", service_cat, provider, tokens, unit, tokens, unit, sku, f"{sku}-p",
        meter, json.dumps(details) if details else "",
    ]  # fmt: skip


def csv_bytes(*rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLS)
    w.writerows(rows)
    return out.getvalue().encode()


I_U = {"TokenDirection": "Input", "TokenCacheAction": "Uncached"}
I_R = {"TokenDirection": "Input", "TokenCacheAction": "Read"}
I_W = {"TokenDirection": "Input", "TokenCacheAction": "Write"}
OUT = {"TokenDirection": "Output"}


@pytest.fixture
def world(env):
    t, other = two_tenants(env)

    class W:
        tenant, other_tenant = t, other

        def session(self, tid=None):
            return app(env, tid or t)

        def load(self, *rows, name="f.csv", tid=None, version="1.5"):
            tid = tid or t
            with self.session(tid) as db:
                cid = imp.get_or_create_manual_connector(db, tid)
                res = imp.import_focus_file(
                    db, tid, cid, name, csv_bytes(*rows), declared_version=version, now=NOW
                )
            assert res.status == "succeeded", res
            return res

        def report(self, tid=None):
            with self.session(tid) as db:
                return ai_token_report(db, START, END)

    return W()


def model(rep, model_id="model-a", provider="Provider One", cur="USD"):
    return next(
        m for m in rep.models if (m.provider, m.model_id, m.currency) == (provider, model_id, cur)
    )


def test_tokens_cost_ratio_and_cache_hit_rate_follow_the_drafts_formulas(world):
    world.load(
        line("3.00", "1000000", props=I_U), line("0.15", "500000", props=I_R, meter="cache read"),
        line("0.30", "100000", props=I_W, meter="cache write"), line("6.00", "400000", props=OUT, meter="out"),
    )  # fmt: skip
    m = model(world.report())
    assert (m.input_tokens, m.output_tokens) == (Decimal(1_600_000), Decimal(400_000))
    assert (m.cache_read_tokens, m.cache_write_tokens) == (Decimal(500_000), Decimal(100_000))
    assert m.input_to_output_ratio == Decimal(4)
    assert m.cache_hit_rate == Decimal(500_000) / Decimal(1_600_000)  # read over ALL input rows
    assert m.effective_cost == Decimal("9.45") and m.unclassified_tokens == 0 and m.warnings == []


def test_cost_per_million_tokens_is_exact_per_row(world):
    world.load(line("3.00", "1000000", props=I_U), line("6.00", "400000", props=OUT))
    rows = {r.direction: r for r in world.report().rows}
    assert rows["Input"].effective_cost_per_million_tokens == Decimal(3)
    assert rows["Output"].effective_cost_per_million_tokens == Decimal(
        15
    )  # 6 / 400,000 * 1,000,000
    assert rows["Output"].model_id == "model-a" and rows["Input"].developer == "Dev One"


def test_rows_without_a_direction_are_counted_not_guessed(world):
    world.load(
        line("3.00", "1000000", props=I_U),
        line("1.00", "50000", props={}),
        line("2.00", "80000", model=None, props={}),
    )
    rep = world.report()
    m = model(rep)
    assert m.input_tokens == Decimal(1_000_000) and m.output_tokens is None
    assert m.unclassified_tokens == Decimal(50_000) and any("no direction" in w for w in m.warnings)
    assert m.input_to_output_ratio is None  # no output rows: unknown, not infinite and not zero
    anon = model(rep, None)
    assert any("did not state a model" in w for w in anon.warnings)
    assert rep.rows_without_model == 1 and rep.rows_without_direction == 2


def test_cache_hit_rate_is_unknown_when_no_input_row_says_anything_about_a_cache(world):
    world.load(
        line("3.00", "1000000", props={"TokenDirection": "Input"}),
        line("6.00", "400000", props=OUT),
    )
    m = model(world.report())
    assert m.cache_hit_rate is None and m.input_to_output_ratio == Decimal("2.5")


def test_a_provider_that_emits_only_cache_read_rows_gets_a_warning_not_a_clean_rate(world):
    world.load(line("0.15", "500000", props=I_R), line("6.00", "400000", props=OUT))
    m = model(world.report())
    assert m.cache_hit_rate == 1 and any("overstated" in w for w in m.warnings)


def test_invalid_property_values_are_treated_as_absent_and_counted(world):
    world.load(
        line("3.00", "1000000", props={"TokenDirection": "Inbound", "TokenCacheAction": "Maybe"})
    )
    rep = world.report()
    assert (
        rep.rows_with_invalid_values == 1
        and rep.rows[0].direction is None
        and rep.rows[0].cache_action is None
    )
    assert model(rep).unclassified_tokens == Decimal(1_000_000)


def test_corrections_are_excluded_from_tokens_and_shown_as_their_own_cost(world):
    world.load(
        line("3.00", "1000000", props=I_U), line("-0.50", "100000", props=I_U, klass="Correction")
    )
    m = model(world.report())
    assert m.input_tokens == Decimal(1_000_000) and m.effective_cost == Decimal(3)
    assert m.correction_effective_cost == Decimal("-0.50")


def test_a_correction_with_no_token_quantity_or_unit_still_shows_its_cost(world):
    world.load(
        line("3.00", "1000000", props=I_U),
        line("-0.75", "", unit="", props=OUT, klass="Correction"),
    )
    m = model(world.report())
    assert m.correction_effective_cost == Decimal("-0.75")  # the money is never hidden
    assert m.input_tokens == Decimal(1_000_000) and m.output_tokens is None  # and it adds no tokens
    assert m.effective_cost == Decimal(3)


def test_only_ai_token_usage_rows_in_the_window_count(world):
    world.load(
        line("3.00", "1000000", props=I_U), line("9.00", "10", props=I_U, service_cat="Compute"),
        line("9.00", "10", props=I_U, unit="Requests"), line("9.00", "10", props=I_U, cat="Purchase"),
        line("9.00", "10", props=I_U, day=2),
    )  # fmt: skip
    rep = world.report()
    assert sum(r.tokens for r in rep.rows) == Decimal(
        1_000_010
    )  # day 1 and day 2 rows, nothing else
    with world.session() as db:
        narrow = ai_token_report(db, START, datetime(2026, 1, 2, tzinfo=UTC))
    assert sum(r.tokens for r in narrow.rows) == Decimal(1_000_000)


def test_token_like_units_other_than_tokens_are_counted_not_summed(world):
    world.load(
        line("3.00", "1000000", props=I_U), line("9.00", "500", props=I_U, unit="1000 Tokens"),
        line("9.00", "500", props=I_U, unit="Token"), line("9.00", "500", props=I_U, unit="Requests"),
    )  # fmt: skip
    rep = world.report()
    assert sum(r.tokens for r in rep.rows) == Decimal(1_000_000)  # only exact "Tokens" is summed
    assert rep.rows_with_other_token_units == 2  # "Requests" is not token-like


def test_currencies_and_providers_are_never_added(world):
    world.load(
        line("3.00", "1000000", props=I_U), line("2.00", "1000000", props=I_U, cur="EUR"),
        line("1.00", "1000000", props=I_U, provider="Provider Two"),
    )  # fmt: skip
    rep = world.report()
    assert len(rep.models) == 3
    assert model(rep, cur="EUR").effective_cost == Decimal(2)


def test_a_revised_export_replaces_earlier_rows_and_other_tenants_see_nothing(world):
    world.load(line("3.00", "1000000", props=I_U), name="a.csv")
    world.load(
        line("4.00", "1000000", props=I_U), name="b.csv"
    )  # same account and window: supersedes
    assert model(world.report()).effective_cost == Decimal(4)
    assert world.report(world.other_tenant).models == []


def test_nothing_imported_is_an_empty_report_not_an_error(world):
    rep = world.report()
    assert (rep.rows, rep.models, rep.truncated) == ([], [], False)
