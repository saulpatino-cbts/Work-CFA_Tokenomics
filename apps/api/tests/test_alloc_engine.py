"""Allocation engine (pure). All data is SYNTHETIC."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

import pytest

from cfa_tokenomics.alloc.engine import (
    MEASURES,
    Condition,
    Context,
    CostLine,
    Rule,
    allocate_line,
    split_exact,
    to_units,
    validate_rule,
)

A, B, C = (uuid.UUID(int=i) for i in (1, 2, 3))
JAN = datetime(2026, 1, 10, tzinfo=UTC)


def D(x):
    return Decimal(str(x))


def line(eff="100", *, tags=None, **fields):
    amounts = {
        "billed": D(eff),
        "effective": D(eff),
        "list": D(eff) * 2,
        "contracted": D(eff) * D("1.5"),
    }
    f = {"service_name": "Bedrock", "sub_account_id": "sub1", "charge_category": "Usage", **fields}
    return CostLine(uuid.uuid4(), amounts, f, tags or {}, JAN)


def rule(method, params, *, key="r", priority=10, conditions=(), version=1):
    return Rule(key, version, priority, method, tuple(conditions), params)


def total(slices, measure="effective"):
    return Decimal(sum(to_units(s.amounts[measure]) for s in slices)).scaleb(-18)


# ---- exact splitting -------------------------------------------------------------------------------


def test_split_exact_gives_the_remainder_deterministically():
    parts = split_exact(D("0.01"), [Fraction(1)] * 3)
    assert sum(parts) == D("0.01")
    assert parts == [
        D("0.003333333333333334"),
        D("0.003333333333333333"),
        D("0.003333333333333333"),
    ]
    assert split_exact(D("0.01"), [Fraction(1)] * 3) == parts  # same input, same answer


def test_split_exact_properties_hold_over_random_cases():
    rng = random.Random(42)
    for _ in range(3000):
        n = rng.randint(1, 7)
        amount = D(rng.choice([-1, 1]) * rng.randint(0, 10**12)) / D(10 ** rng.randint(0, 18))
        weights = [Fraction(rng.randint(0, 50), rng.randint(1, 9)) for _ in range(n)]
        if sum(weights) == 0:
            weights[0] = Fraction(1)
        parts = split_exact(amount, weights)
        # The invariant, in exact integer units: nothing created or lost. (Decimal sum() would round
        # to the ambient 28-digit context and could hide an error.)
        assert sum(to_units(p) for p in parts) == to_units(amount), (amount, weights)
        ideal = [Fraction(abs(to_units(amount))) * w / sum(weights) for w in weights]
        for p, i in zip(parts, ideal, strict=True):
            assert abs(Fraction(abs(to_units(p))) - i) < 1  # never more than one unit from ideal
            assert p == 0 or (p < 0) == (amount < 0)  # sign is preserved
        assert [p for p, w in zip(parts, weights, strict=True) if w == 0] == [0] * weights.count(0)


def test_split_exact_is_exact_for_38_digit_amounts_whatever_the_decimal_context():
    from decimal import localcontext

    big = D("99999999999999999999.999999999999999999")  # NUMERIC(38,18) maximum
    with localcontext() as ctx:
        ctx.prec = 5  # a hostile ambient precision must not matter
        parts = split_exact(big, [Fraction(1), Fraction(1), Fraction(1)])
        assert sum(to_units(p) for p in parts) == to_units(big)
        assert to_units(parts[0]) in (to_units(big) // 3, to_units(big) // 3 + 1)
        assert to_units(D("0.000000000000000001")) == 1 and to_units(D("-1E+2")) == -100 * 10**18
    assert str(split_exact(D("7.5"), [Fraction(1)])[0]) == "7.500000000000000000"


def test_split_exact_refuses_bad_input():
    with pytest.raises(ValueError):
        split_exact(D(1), [])
    with pytest.raises(ValueError):
        split_exact(D(1), [Fraction(0), Fraction(0)])
    with pytest.raises(ValueError):
        split_exact(D(1), [Fraction(-1), Fraction(2)])
    with pytest.raises(ValueError, match="decimal places"):
        split_exact(D("0.0000000000000000001"), [Fraction(1)])


# ---- methods ---------------------------------------------------------------------------------------


def test_direct_allocates_everything_to_one_application():
    s = allocate_line(line(), [rule("direct", {"application_id": str(A)})], Context())
    assert [(x.application_id, x.method, x.share) for x in s] == [(A, "direct", 1)]
    assert total(s) == 100


def test_tag_rule_resolves_by_application_name_or_explicit_map():
    ctx = Context(apps_by_name={"claims-bot": A})
    by_name = allocate_line(
        line(tags={"app": "claims-bot"}), [rule("tag", {"tag_key": "app"})], ctx
    )
    assert by_name[0].application_id == A and by_name[0].method == "tag"
    mapped = allocate_line(
        line(tags={"app": "legacy-7"}),
        [rule("tag", {"tag_key": "app", "map": {"legacy-7": str(B)}})],
        ctx,
    )
    assert mapped[0].application_id == B


def test_tags_are_case_sensitive_and_never_guessed():
    ctx = Context(apps_by_name={"claims-bot": A})
    r = [rule("tag", {"tag_key": "app"})]
    wrong_case = allocate_line(line(tags={"app": "Claims-Bot"}), r, ctx)
    assert (wrong_case[0].application_id, wrong_case[0].reason) == (None, "tag_unmapped")
    wrong_key = allocate_line(line(tags={"App": "claims-bot"}), r, ctx)
    assert wrong_key[0].reason == "tag_missing"
    assert total(wrong_key) == 100  # the money is still accounted for, in the unallocated bucket


def test_fixed_percent_sends_the_remainder_to_unallocated_with_a_reason():
    params = {
        "targets": [
            {"application_id": str(A), "percent": "60"},
            {"application_id": str(B), "percent": "25"},
        ]
    }
    s = allocate_line(line("100"), [rule("fixed_percent", params)], Context())
    assert [(x.application_id, x.amounts["effective"], x.reason) for x in s] == [
        (A, D(60), None), (B, D(25), None), (None, D(15), "percent_remainder"),
    ]  # fmt: skip
    full = {
        "targets": [
            {"application_id": str(A), "percent": "70"},
            {"application_id": str(B), "percent": "30"},
        ]
    }
    assert [
        x.application_id for x in allocate_line(line(), [rule("fixed_percent", full)], Context())
    ] == [A, B]


def test_even_split_is_exact_even_when_it_does_not_divide():
    s = allocate_line(
        line("100"), [rule("even", {"application_ids": [str(A), str(B), str(C)]})], Context()
    )
    assert total(s) == 100 and len(s) == 3
    assert max(x.amounts["effective"] for x in s) - min(x.amounts["effective"] for x in s) <= D(
        "1e-18"
    )


def test_proportional_uses_drivers_for_the_period_and_the_latest_version():
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    ctx = Context(drivers={
        ("p", A): [(start, end, 1, D(10)), (start, end, 2, D(75))],  # version 2 wins
        ("p", B): [(start, end, 1, D(25))],
    })  # fmt: skip
    s = allocate_line(
        line("100"), [rule("proportional", {"application_ids": [str(A), str(B)]}, key="p")], ctx
    )
    assert [x.amounts["effective"] for x in s] == [D(75), D(25)]


def test_proportional_needs_every_driver_and_a_positive_total():
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    r = [rule("proportional", {"application_ids": [str(A), str(B)]}, key="p")]
    missing = allocate_line(line(), r, Context(drivers={("p", A): [(start, end, 1, D(1))]}))
    assert missing[0].reason == "driver_missing" and missing[0].application_id is None
    zero = allocate_line(
        line(),
        r,
        Context(drivers={("p", A): [(start, end, 1, D(0))], ("p", B): [(start, end, 1, D(0))]}),
    )
    assert zero[0].reason == "driver_zero"
    other_month = Context(
        drivers={
            ("p", A): [(datetime(2025, 12, 1, tzinfo=UTC), start, 1, D(1))],
            ("p", B): [(start, end, 1, D(1))],
        }
    )
    assert allocate_line(line(), r, other_month)[0].reason == "driver_missing"


# ---- rule order, conditions and fall-through -------------------------------------------------------


def test_priority_decides_and_an_inapplicable_rule_falls_through():
    tag = rule("tag", {"tag_key": "app"}, key="by-tag", priority=1)
    catch_all = rule("direct", {"application_id": str(C)}, key="shared", priority=99)
    ctx = Context(apps_by_name={"a": A})
    assert allocate_line(line(tags={"app": "a"}), [catch_all, tag], ctx)[0].application_id == A
    assert (
        allocate_line(line(), [catch_all, tag], ctx)[0].application_id == C
    )  # tag missing, so fall through
    only_tag = allocate_line(line(), [tag], ctx)
    assert (only_tag[0].application_id, only_tag[0].reason) == (
        None,
        "tag_missing",
    )  # the informative reason survives


def test_no_matching_rule_is_unallocated_not_lost():
    s = allocate_line(line(), [], Context())
    assert (
        len(s) == 1
        and s[0].application_id is None
        and s[0].reason == "no_rule"
        and s[0].method == "unallocated"
    )
    assert all(s[0].amounts[m] == line().amounts[m] for m in MEASURES)


def test_conditions_eq_prefix_in_exists_and_tags():
    r = lambda c: [rule("direct", {"application_id": str(A)}, conditions=c)]  # noqa: E731
    ctx = Context()
    assert (
        allocate_line(line(), r([Condition("service_name", "eq", "Bedrock")]), ctx)[
            0
        ].application_id
        == A
    )
    assert (
        allocate_line(line(), r([Condition("service_name", "eq", "bedrock")]), ctx)[
            0
        ].application_id
        is None
    )
    assert (
        allocate_line(
            line(resource_id="arn:aws:x/1"),
            r([Condition("resource_id", "prefix", "arn:aws:x/")]),
            ctx,
        )[0].application_id
        == A
    )
    assert (
        allocate_line(line(), r([Condition("sub_account_id", "in", ["sub1", "sub2"])]), ctx)[
            0
        ].application_id
        == A
    )
    assert (
        allocate_line(line(), r([Condition("resource_id", "exists")]), ctx)[0].application_id
        is None
    )
    assert (
        allocate_line(line(), r([Condition("resource_id", "not_exists")]), ctx)[0].application_id
        == A
    )
    assert (
        allocate_line(line(tags={"env": "prod"}), r([Condition("tag:env", "eq", "prod")]), ctx)[
            0
        ].application_id
        == A
    )
    both = r([Condition("tag:env", "eq", "prod"), Condition("service_name", "eq", "Other")])
    assert (
        allocate_line(line(tags={"env": "prod"}), both, ctx)[0].application_id is None
    )  # all conditions must hold


# ---- the invariant, for every measure --------------------------------------------------------------


@pytest.mark.parametrize("eff", ["100", "0.01", "-37.5", "0", "1234567.123456789012345678"])
def test_every_measure_sums_exactly_for_every_method(eff):
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    ctx = Context(
        apps_by_name={"a": A},
        drivers={("p", A): [(start, end, 1, D(3))], ("p", B): [(start, end, 1, D(7))]},
    )
    rules_by_method = [
        rule("direct", {"application_id": str(A)}),
        rule("tag", {"tag_key": "app"}),
        rule(
            "fixed_percent",
            {
                "targets": [
                    {"application_id": str(A), "percent": "33.333"},
                    {"application_id": str(B), "percent": "33.333"},
                ]
            },
        ),
        rule("even", {"application_ids": [str(A), str(B), str(C)]}),
        rule("proportional", {"application_ids": [str(A), str(B)]}, key="p"),
    ]
    for r in rules_by_method:
        ln = line(eff, tags={"app": "a"})
        slices = allocate_line(ln, [r], ctx)
        for m in MEASURES:
            assert total(slices, m) == ln.amounts[m], (r.method, m)


def test_a_commitment_purchase_allocates_its_zero_effective_cost_without_error():
    ln = CostLine(
        uuid.uuid4(),
        {"billed": D(1000), "effective": D(0), "list": D(1000), "contracted": D(1000)},
        {"charge_category": "Purchase"},
        {},
        JAN,
    )
    s = allocate_line(ln, [rule("direct", {"application_id": str(A)})], Context())
    assert (s[0].amounts["billed"], s[0].amounts["effective"]) == (1000, 0)


def test_allocation_is_deterministic():
    ctx = Context()
    r = [rule("even", {"application_ids": [str(A), str(B), str(C)]})]
    ln = line("10")
    assert allocate_line(ln, r, ctx) == allocate_line(ln, r, ctx)


# ---- rule validation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "params", "conds"),
    [
        ("magic", {}, []),
        ("direct", {}, []),
        ("direct", {"application_id": "not-a-uuid"}, []),
        ("tag", {}, []),
        ("tag", {"tag_key": "app", "map": {"x": "nope"}}, []),
        ("fixed_percent", {"targets": []}, []),
        (
            "fixed_percent",
            {
                "targets": [
                    {"application_id": str(A), "percent": "60"},
                    {"application_id": str(B), "percent": "50"},
                ]
            },
            [],
        ),
        ("fixed_percent", {"targets": [{"application_id": str(A), "percent": "0"}]}, []),
        (
            "fixed_percent",
            {
                "targets": [
                    {"application_id": str(A), "percent": "10"},
                    {"application_id": str(A), "percent": "10"},
                ]
            },
            [],
        ),
        ("even", {"application_ids": [str(A)]}, []),
        ("proportional", {"application_ids": []}, []),
        ("even", {"application_ids": [str(A), str(A)]}, []),
        ("direct", {"application_id": str(A)}, [Condition("nonsense", "eq", "x")]),
        ("direct", {"application_id": str(A)}, [Condition("service_name", "regex", ".*")]),
        ("direct", {"application_id": str(A)}, [Condition("service_name", "in", [])]),
        ("direct", {"application_id": str(A)}, [Condition("tag:", "eq", "x")]),
        ("direct", {"application_id": str(A)}, [Condition("service_name", "eq", 5)]),
    ],
)
def test_malformed_rules_are_refused_when_created(method, params, conds):
    with pytest.raises(ValueError):
        validate_rule(method, params, conds)


def test_well_formed_rules_validate():
    validate_rule("direct", {"application_id": str(A)}, [Condition("tag:team", "exists")])
    validate_rule(
        "fixed_percent",
        {
            "targets": [
                {"application_id": str(A), "percent": "60"},
                {"application_id": str(B), "percent": "40"},
            ]
        },
        [],
    )
    validate_rule(
        "proportional",
        {"application_ids": [str(A), str(B)]},
        [Condition("service_name", "in", ["a", "b"])],
    )


def test_a_value_less_tag_exists_but_cannot_name_an_application():
    """FOCUS stores a tag key without a value as boolean true."""
    ctx = Context(apps_by_name={"True": A, "true": A})
    s = allocate_line(line(tags={"app": True}), [rule("tag", {"tag_key": "app"})], ctx)
    assert (s[0].application_id, s[0].reason) == (None, "tag_without_value")
    exists = rule("direct", {"application_id": str(B)}, conditions=[Condition("tag:app", "exists")])
    assert allocate_line(line(tags={"app": True}), [exists], ctx)[0].application_id == B
    is_true = rule(
        "direct", {"application_id": str(B)}, conditions=[Condition("tag:app", "eq", "true")]
    )
    assert allocate_line(line(tags={"app": True}), [is_true], ctx)[0].application_id == B


def test_rules_can_target_provider_split_rows():
    r = rule(
        "direct",
        {"application_id": str(A)},
        conditions=[Condition("allocated_method_id", "exists")],
    )
    assert (
        allocate_line(line(allocated_method_id="split-v1"), [r], Context())[0].application_id == A
    )
    assert allocate_line(line(), [r], Context())[0].application_id is None
