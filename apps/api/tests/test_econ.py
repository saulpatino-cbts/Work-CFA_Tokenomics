"""Economics engine. The worked example from docs/economics/05-calculation-engine.md must reproduce exactly.
All figures are ILLUSTRATIVE placeholders, not provider prices or marketplace fees."""

from decimal import Decimal

import pytest

from cfa_tokenomics.econ import commercial as com
from cfa_tokenomics.econ import formulas as f
from cfa_tokenomics.econ import scenario as sc
from cfa_tokenomics.econ.node import Status, leaf
from cfa_tokenomics.econ.types import CTX, Basis, D

USD = "USD"
OBS, E, A = Basis.OBSERVED, Basis.ESTIMATED, Basis.ASSUMED


def q4(n, places="0.0001"):
    return n.value.quantize(Decimal(places))


def money(key, v, basis, unit="money"):
    return leaf(key, v, unit, basis, USD)


def example(**override):
    base = dict(
        currency=USD,
        users=leaf("users", 100, "users", A),
        adoption=leaf("adoption", 1, "ratio", A),
        interactions_per_user=leaf("interactions_per_user", 40, "interactions", A),
        tokens_per_interaction={
            "input": leaf("tpi.input", 10000, "tokens", A),
            "output": leaf("tpi.output", 2500, "tokens", A),
        },
        models=(
            sc.ModelLine(
                "m",
                leaf("share", 1, "ratio", A),
                {
                    "input": leaf("price.input", 3, "USD/1M tokens", E, USD),
                    "output": leaf("price.output", 15, "USD/1M tokens", E, USD),
                },
            ),
        ),
        transactions_per_user=leaf("txn_per_user", 15, "transactions", A),
        infra_fixed=money("infra", 600, OBS),
        supporting_api=money("supporting", 0, OBS),
        licence=money("licence", 200, OBS),
        ops_hours=leaf("ops_hours", 10, "hours", A),
        ops_rate=money("ops_rate", 90, A, "money/hour"),
        dev_investment=money("investment", 120000, A),
        dev_months=leaf("dev_months", 24, "months", A),
        baseline_hours_per_txn=leaf("base_h", "0.5", "hours", A),
        assisted_hours_per_txn=leaf("assisted_h", "0.2", "hours", A),
        loaded_rate=money("loaded_rate", 85, A, "money/hour"),
        realization=leaf("realization", "0.7", "ratio", A),
        cashability=leaf("cashability", "0.25", "ratio", A),
        target_margin=leaf("target_margin", "0.40", "ratio", A),
        marketplace_fee_rate=leaf("fee_rate", "0.03", "ratio", A),
    )
    base.update(override)
    return sc.ScenarioInputs(**base)


# ---- the worked example reproduces exactly ---------------------------------------------------------


def test_worked_example_cost():
    r = sc.evaluate(example())
    assert r["tokens.input"].value == 40_000_000 and r["tokens.output"].value == 10_000_000
    assert r["ai_cost"].value == 270
    assert r["tca"].value == 6970
    assert r["run_cost"].value == 1970
    assert r["tca"].value - r["run_cost"].value == r["dev_cost"].value == 5000


def test_worked_example_value_roi_payback():
    r = sc.evaluate(example())
    assert r["hours_saved"].value == 315
    assert r["labor_value_capacity"].value == 26775
    assert r["labor_value_cashable"].value == Decimal("6693.75")
    assert r["net_value_capacity"].value == 19805
    assert r["net_value_cashable"].value == Decimal("-276.25")
    assert q4(r["roi_capacity"]) == Decimal("2.8415")
    assert q4(r["roi_cashable"]) == Decimal("-0.0396")
    assert q4(r["payback_capacity"], "0.01") == Decimal("4.84")
    assert q4(r["payback_cashable"], "0.01") == Decimal("25.40")


def test_worked_example_pricing_and_margin():
    r = sc.evaluate(example())
    assert q4(r["required_price"], "0.01") == Decimal("3456.14")
    priced = sc.evaluate(example(price=money("price", r["required_price"].value, A)))
    assert q4(priced["gross_margin"]) == Decimal("0.4000")


def test_payback_uses_run_cost_not_tca():
    r = sc.evaluate(example())
    right = Decimal(120000) / (Decimal(26775) - Decimal(1970))
    wrong = Decimal(120000) / (Decimal(26775) - Decimal(6970))
    assert r["payback_capacity"].value.quantize(Decimal("0.0001")) == right.quantize(
        Decimal("0.0001")
    )
    assert r["payback_capacity"].value != wrong


def test_unit_costs():
    r = sc.evaluate(example())
    assert r["cost_per_interaction"].value == CTX.divide(Decimal(6970), Decimal(4000))
    assert r["cost_per_transaction"].value == CTX.divide(Decimal(6970), Decimal(1500))
    assert r["cost_per_active_user"].value == Decimal("69.7")
    assert r["run_cost_per_interaction"].value == CTX.divide(Decimal(1970), Decimal(4000))


# ---- basis and provenance --------------------------------------------------------------------------


def test_estimated_cost_is_never_labelled_observed():
    # Observed token counts priced from a price book give an ESTIMATED cost, never an observed one.
    observed_tokens = leaf("tokens", 40_000_000, "tokens", OBS)
    price = leaf("price", 3, "USD/1M tokens", E, USD)
    cost = f.ai_cost_estimate([(observed_tokens, price)])
    assert cost.value == 120 and cost.basis is E and cost.mix.observed == 0


def test_assumed_volumes_make_the_cost_assumed():
    # In the example scenario the token volumes are themselves assumptions, so the cost is assumption-dependent.
    ai = sc.evaluate(example())["ai_cost"]
    assert ai.basis is A and ai.mix.assumption_dependent


def test_observed_quantity_and_observed_price_stay_observed():
    cost = f.ai_cost_estimate(
        [(leaf("t", 1_000_000, "tokens", OBS), leaf("p", 4, "USD/1M tokens", OBS, USD))]
    )
    assert (
        cost.basis is OBS
    )  # e.g. an invoiced unit price; the rule is the weakest input, not a blanket upgrade


def test_sum_basis_mix_is_value_weighted():
    mix = sc.evaluate(example())["tca"].mix
    total = Decimal(6970)
    assert abs(mix.observed - Decimal(800) / total) < Decimal("1e-20")  # infrastructure + licence
    assert mix.estimated == 0
    assert abs(mix.assumed - Decimal(6170) / total) < Decimal(
        "1e-20"
    )  # AI volumes, ops, development
    assert mix.assumption_dependent


def test_sum_mix_with_observed_estimated_and_assumed_parts():
    parts = [
        leaf("a", 100, "money", OBS, USD),
        leaf("b", 300, "money", E, USD),
        leaf("c", 600, "money", A, USD),
    ]
    mix = f.total("t", "t", 1, parts).mix
    assert (mix.observed, mix.estimated, mix.assumed) == (
        Decimal("0.1"),
        Decimal("0.3"),
        Decimal("0.6"),
    )


def test_products_and_ratios_take_the_weakest_basis():
    r = sc.evaluate(example())
    assert r["roi_capacity"].basis is A
    ops = f.ops_cost(leaf("h", 10, "hours", OBS), money("r", 90, OBS, "money/hour"))
    assert ops.basis is OBS


def test_explain_walk_reaches_leaf_inputs():
    r = sc.evaluate(example())
    nodes = list(r["roi_capacity"].walk())
    leaves = {n.key for n in nodes if n.formula_id == "input"}
    assert {
        "price.input",
        "ops_hours",
        "licence",
        "realization",
        "loaded_rate",
        "investment",
    } <= leaves
    assert all(n.mix is not None and n.formula_version >= 1 for n in nodes)


def test_deterministic_ids_and_change_detection():
    a, b = sc.evaluate(example()), sc.evaluate(example())
    assert a["roi_capacity"].id == b["roi_capacity"].id
    c = sc.evaluate(example(users=leaf("users", 101, "users", A)))
    assert c["roi_capacity"].id != a["roi_capacity"].id


# ---- unknown is not zero; refusals -----------------------------------------------------------------


def test_unknown_input_makes_results_unknown_not_zero():
    r = sc.evaluate(example(ops_hours=leaf("ops_hours", None, "hours", A)))
    for k in ("ops_cost", "tca", "run_cost", "roi_capacity", "payback_capacity"):
        assert r[k].status is Status.UNKNOWN and r[k].value is None
    assert r["ai_cost"].known  # unaffected parts stay known


def test_floats_are_refused():
    with pytest.raises(TypeError):
        D(1.5)
    with pytest.raises(TypeError):
        leaf("x", 1.5, "money", A, USD)
    with pytest.raises(TypeError):
        D(True)


def test_mixed_currencies_are_refused():
    with pytest.raises(ValueError, match="currencies"):
        f.total("t", "t", 1, [leaf("a", 1, "money", OBS, "USD"), leaf("b", 1, "money", OBS, "EUR")])


def test_domain_checks():
    with pytest.raises(ValueError):
        sc.evaluate(example(adoption=leaf("adoption", "1.5", "ratio", A)))
    with pytest.raises(ValueError):
        sc.evaluate(example(dev_months=leaf("dev_months", 0, "months", A)))
    with pytest.raises(ValueError, match="shares"):
        m = example().models[0]
        sc.evaluate(example(models=(m, m)))


def test_missing_price_is_an_error_not_zero():
    m = sc.ModelLine(
        "m", leaf("share", 1, "ratio", A), {"input": leaf("p", 3, "USD/1M tokens", E, USD)}
    )
    with pytest.raises(ValueError, match="not zero"):
        sc.evaluate(example(models=(m,)))


def test_payback_not_reached_and_zero_units():
    r = sc.evaluate(example(loaded_rate=money("loaded_rate", 1, A, "money/hour")))
    assert (
        r["payback_capacity"].status is Status.NOT_REACHED and r["payback_capacity"].value is None
    )
    zero = sc.evaluate(example(adoption=leaf("adoption", 0, "ratio", A)))
    assert zero["cost_per_interaction"].status is Status.INFEASIBLE


# ---- scenarios scale through the same formulas -----------------------------------------------------


def test_ten_times_usage_scales_ai_cost_linearly():
    r = sc.evaluate(example(users=leaf("users", 1000, "users", A)))
    assert r["tokens.input"].value == 400_000_000
    assert r["ai_cost"].value == 2700


def test_infrastructure_step_function():
    step = (leaf("cap", 5000, "interactions", A), money("step_cost", 400, A))
    base = sc.evaluate(example(infra_step=step))
    assert base["infra_cost"].value == 600 + 400  # 4,000 interactions -> 1 step
    big = sc.evaluate(example(infra_step=step, users=leaf("users", 1000, "users", A)))
    assert big["infra_cost"].value == 600 + 8 * 400  # 40,000 interactions -> 8 steps


def test_model_change_and_mix():
    cheap = {
        "input": leaf("p1", 1, "USD/1M tokens", E, USD),
        "output": leaf("p2", 5, "USD/1M tokens", E, USD),
    }
    dear = example().models[0]
    only_cheap = sc.evaluate(example(models=(sc.ModelLine("c", leaf("s", 1, "ratio", A), cheap),)))
    assert only_cheap["ai_cost"].value == 40 * 1 + 10 * 5
    half = sc.evaluate(
        example(
            models=(
                sc.ModelLine("c", leaf("s1", "0.5", "ratio", A), cheap),
                sc.ModelLine("d", leaf("s2", "0.5", "ratio", A), dear.prices),
            )
        )
    )
    assert half["ai_cost"].value == (90 + 270) / 2


def test_variable_infrastructure_per_interaction():
    r = sc.evaluate(
        example(infra_variable_per_interaction=money("v", "0.05", A, "money/interaction"))
    )
    assert r["infra_cost"].value == 600 + 4000 * Decimal("0.05")


def test_optional_value_components_add_to_both_variants():
    avoided = money("avoided", 1000, A)
    r = sc.evaluate(example(avoided_cost=avoided))
    assert r["business_value_capacity"].value == 26775 + 1000
    assert (
        r["business_value_cashable"].value == Decimal("6693.75") + 1000
    )  # only labour is discounted


def test_value_chain_skipped_when_value_inputs_absent():
    r = sc.evaluate(example(baseline_hours_per_txn=None))
    assert "roi_capacity" not in r and "tca" in r


# ---- sensitivity -----------------------------------------------------------------------------------


def test_tornado_orders_by_swing_and_marks_hypotheticals_assumed():
    inp = example()
    rows = sc.tornado(
        inp,
        {
            "realization": ("0.4", "1"),
            "loaded_rate": (60, 120),
            "ops_hours": (5, 15),
            "users": (50, 150),
        },
        "roi_capacity",
    )
    swings = [r["swing"] for r in rows]
    assert swings == sorted(swings, reverse=True)
    assert rows[0]["path"] in ("realization", "loaded_rate", "users")
    assert all(r["low"].known and r["high"].known for r in rows)
    changed = sc.with_value(inp, "users", 50)
    assert changed.users.basis is A and changed.users.source_ref.startswith("sensitivity of")
    assert inp.users.value == 100  # inputs are not mutated


def test_nested_paths_and_grid():
    inp = example()
    cheaper = sc.with_value(inp, "models.0.prices.input", 1)
    assert sc.evaluate(cheaper)["ai_cost"].value == 40 * 1 + 10 * 15
    g = sc.grid(inp, "users", [50, 100, 200], "realization", ["0.5", "1"], "roi_capacity")
    assert len(g) == 2 and all(len(row) == 3 for row in g)
    assert g[1][1].value > g[0][1].value  # higher realization, higher ROI


def test_tornado_puts_unknown_outputs_last():
    inp = example(realization=leaf("realization", None, "ratio", A))
    rows = sc.tornado(inp, {"users": (50, 150)}, "roi_capacity")
    assert rows[0]["swing"] is None  # the output is unknown whatever the driver does


# ---- commercial ------------------------------------------------------------------------------------


def test_required_price_edge_cases():
    cogs = money("cogs", 1970, OBS)
    ok = com.required_price(cogs, leaf("f", "0.03", "ratio", A), leaf("m", "0.40", "ratio", A))
    assert q4(ok, "0.01") == Decimal("3456.14")
    bad = com.required_price(cogs, leaf("f", "0.03", "ratio", A), leaf("m", "0.97", "ratio", A))
    assert bad.status is Status.INFEASIBLE and bad.value is None
    with_fixed = com.required_price(
        cogs, leaf("f", "0.03", "ratio", A), leaf("m", "0.40", "ratio", A), money("fx", 100, A)
    )
    assert with_fixed.value == CTX.divide(Decimal(2070), Decimal("0.57"))
    with pytest.raises(ValueError):
        com.required_price(cogs, leaf("f", "1", "ratio", A), leaf("m", "0", "ratio", A))


def test_marketplace_fee_and_margin_identity():
    rev = money("rev", 10000, A)
    fee = com.marketplace_fee(rev, leaf("f", "0.03", "ratio", A), money("fx", 100, A))
    assert fee.value == 400
    gm = com.gross_margin(rev, fee, money("cogs", 5000, OBS))
    assert gm.value == Decimal("0.46")
    assert com.gross_margin(money("r", 0, A), fee, money("c", 1, A)).status is Status.INFEASIBLE


def test_fee_schedule_is_configuration_not_a_constant():
    r1 = com.marketplace_fee(money("rev", 1000, A), leaf("f", "0.03", "ratio", A))
    r2 = com.marketplace_fee(money("rev", 1000, A), leaf("f", "0.20", "ratio", A))
    assert (r1.value, r2.value) == (30, 200)


def test_tiered_pricing_graduated_and_volume():
    tiers = [
        (D(100), money("t1", "1.00", A)),
        (D(500), money("t2", "0.80", A)),
        (None, money("t3", "0.50", A)),
    ]
    q = lambda n: leaf("q", n, "units", OBS)  # noqa: E731
    assert com.revenue_tiered("r", q(700), tiers).value == 100 + 320 + 100
    assert com.revenue_tiered("r", q(50), tiers).value == 50
    assert com.revenue_tiered("r", q(100), tiers).value == 100  # exactly at a bound
    assert com.revenue_tiered("r", q(700), tiers, "volume").value == 350
    assert com.revenue_tiered("r", q(300), tiers, "volume").value == 240
    with pytest.raises(ValueError):
        com.revenue_tiered("r", q(1), tiers, "bogus")


def test_revenue_models():
    users = leaf("u", 100, "users", OBS)
    assert com.revenue_linear("r", users, money("p", 20, A), money("fx", 50, A)).value == 2050
    use = com.revenue_usage(
        "r",
        [
            (leaf("in", 40_000_000, "tokens", OBS), money("p1", 10, A)),
            (leaf("out", 10_000_000, "tokens", OBS), money("p2", 30, A)),
        ],
        per=D(1_000_000),
    )
    assert use.value == 700


def test_break_even_and_unit_price():
    fixed, unit, var, fee = (
        money("f", 5000, A),
        money("p", 50, A),
        money("v", 20, A),
        leaf("fee", "0.03", "ratio", A),
    )
    n = com.break_even_volume(fixed, unit, var, fee)
    assert q4(n, "0.001") == Decimal("175.439")
    assert com.break_even_volume(fixed, unit, money("v", 60, A), fee).status is Status.INFEASIBLE
    up = com.required_unit_price(
        var, fixed, leaf("n", 1000, "units", A), fee, leaf("m", "0.40", "ratio", A)
    )
    assert up.value == CTX.divide(Decimal(25), Decimal("0.57"))


def test_commitment_spend_and_waste():
    commit = money("c", 1000, A)
    over = com.committed_spend(commit, money("u", 1500, OBS), leaf("o", "1.2", "ratio", A))
    assert over.value == 1600
    under = com.committed_spend(commit, money("u", 700, OBS), leaf("o", "1.2", "ratio", A))
    assert under.value == 1000
    assert com.commitment_waste(commit, money("u", 700, OBS)).value == 300
    assert com.commitment_waste(commit, money("u", 1500, OBS)).value == 0


def test_loaded_rate_formula():
    r = f.loaded_rate(
        money("s", 120000, A), leaf("b", "0.25", "ratio", A), leaf("h", 1800, "hours", A)
    )
    assert q4(r, "0.01") == Decimal("83.33")
    with pytest.raises(ValueError):
        f.loaded_rate(money("s", 1, A), leaf("b", 0, "ratio", A), leaf("h", 0, "hours", A))


def test_error_and_revenue_value_components():
    ev = f.error_value(
        leaf("be", 100, "errors", OBS), leaf("ae", 40, "errors", A), money("c", 50, A)
    )
    assert ev.value == 3000
    rv = f.revenue_value(money("up", 10000, A), leaf("cm", "0.35", "ratio", A))
    assert rv.value == 3500
    with pytest.raises(ValueError):
        f.revenue_value(money("up", 1, A), leaf("cm", "1.5", "ratio", A))


def test_canon_is_exact_and_independent_of_scale():
    from decimal import localcontext

    from cfa_tokenomics.econ.types import canon

    assert canon(Decimal("315.0")) == canon(Decimal("315")) == "315"
    assert canon(Decimal("1E+3")) == "1000" and canon(Decimal("0E-69")) == "0"
    assert canon(Decimal("-0.50")) == "-0.5"
    long = Decimal("0.1147776183644189383070301291248206")
    with localcontext() as ctx:
        ctx.prec = 5  # a low-precision ambient context must not change the text
        assert canon(long) == "0.1147776183644189383070301291248206"
    with pytest.raises(ValueError):
        canon(Decimal("NaN"))


def test_node_id_does_not_depend_on_the_ambient_decimal_context():
    from decimal import localcontext

    from cfa_tokenomics.econ.types import BasisMix

    mix = BasisMix(
        Decimal("0.1147776183644189383070301291248206"),
        Decimal(0),
        Decimal("0.8852223816355810616929698708751794"),
    )
    from cfa_tokenomics.econ.node import Node

    def make():
        return Node("k", "f", 1, Decimal("6970"), "money", "USD", mix)

    with localcontext() as ctx:
        ctx.prec = 5
        low = make().id
    with localcontext() as ctx:
        ctx.prec = 60
        high = make().id
    assert low == high == make().id
