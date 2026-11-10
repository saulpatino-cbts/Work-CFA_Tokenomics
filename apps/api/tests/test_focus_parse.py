"""FOCUS CSV parser. Every file here is SYNTHETIC and labelled as such; none is a real export."""

import gzip
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cfa_tokenomics.focus.parse import FileError, parse_focus_csv

HEAD = "BilledCost,EffectiveCost,ListCost,ContractedCost,ChargeCategory,ChargePeriodStart,ChargePeriodEnd,BillingCurrency"
OK = "1.5,1.5,2,1.8,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD"


def csv(*rows, head=HEAD):
    return ("\n".join([head, *rows]) + "\n").encode()


def reasons(result):
    return [(r.row_number, r.reason, r.column) for r in result.rejects]


def test_a_valid_row_is_parsed_exactly():
    r = parse_focus_csv(csv(OK))
    assert r.rejects == [] and len(r.rows) == 1
    v = r.rows[0].values
    assert v["billed_cost"] == Decimal("1.5") and v["list_cost"] == Decimal(2)
    assert v["charge_period_start"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert v["charge_category"] == "Usage" and v["billing_currency"] == "USD"
    assert r.rows[0].row_number == 2  # the header is row 1


def test_decimals_are_exact_not_binary_floats():
    r = parse_focus_csv(
        csv("0.1,0.2,0.3,0.300000000000000001,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD")
    )
    v = r.rows[0].values
    assert v["billed_cost"] + v["effective_cost"] == Decimal("0.3")
    assert v["contracted_cost"] == Decimal("0.300000000000000001")


def test_optional_columns_tags_and_unknown_columns_are_kept():
    head = HEAD + ",ServiceName,Tags,ConsumedQuantity,x_SkuMeterId,x_Empty"
    row = OK + ',Amazon Bedrock,"{""app"": ""claims""}",1000000.5,abc-123,'
    r = parse_focus_csv(csv(row, head=head))
    v = r.rows[0]
    assert v.values["service_name"] == "Amazon Bedrock"
    assert v.values["tags"] == {"app": "claims"}
    assert v.values["consumed_quantity"] == Decimal("1000000.5")
    assert r.unknown_columns == ["x_SkuMeterId", "x_Empty"]
    assert v.extensions == {"x_SkuMeterId": "abc-123"}  # empty cells are not stored


def test_negative_costs_are_allowed_for_credits_and_adjustments():
    r = parse_focus_csv(csv("-5,-5,-5,-5,Credit,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD"))
    assert r.rows[0].values["billed_cost"] == -5 and r.rejects == []


def test_missing_required_columns_fail_the_whole_file_and_name_them():
    with pytest.raises(FileError, match="ListCost, ContractedCost"):
        parse_focus_csv(csv("1,1,USD", head="BilledCost,EffectiveCost,BillingCurrency"))


@pytest.mark.parametrize(
    ("row", "reason", "column"),
    [
        (
            "1,1,1,1,Rebate,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "unknown_charge_category",
            "ChargeCategory",
        ),
        (
            "1,1,1,1,usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "unknown_charge_category",
            "ChargeCategory",
        ),
        (
            "abc,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "not_a_number",
            "BilledCost",
        ),
        (
            "NaN,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "not_finite",
            "BilledCost",
        ),
        (
            "Infinity,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "not_finite",
            "BilledCost",
        ),
        (
            ",1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "missing_required_value",
            "BilledCost",
        ),
        (
            "1,1,1,1.0000000000000000001,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "too_many_decimals",
            "ContractedCost",
        ),
        (
            "1,1,1,1,Usage,2026-01-01T00:00:00,2026-01-02T00:00:00Z,USD",
            "timestamp_without_timezone",
            "ChargePeriodStart",
        ),
        ("1,1,1,1,Usage,yesterday,2026-01-02T00:00:00Z,USD", "bad_timestamp", "ChargePeriodStart"),
        (
            "1,1,1,1,Usage,2026-01-02T00:00:00Z,2026-01-02T00:00:00Z,USD",
            "charge_period_not_positive",
            "ChargePeriodEnd",
        ),
        (
            "1,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,dollars",
            "bad_currency",
            "BillingCurrency",
        ),
        (
            "1,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,",
            "missing_required_value",
            "BillingCurrency",
        ),
    ],
)
def test_a_bad_row_is_rejected_with_a_reason_and_good_rows_survive(row, reason, column):
    r = parse_focus_csv(csv(OK, row, OK))
    assert len(r.rows) == 2 and reasons(r) == [(3, reason, column)]


def test_too_many_decimals_is_refused_never_rounded_but_trailing_zeros_are_fine():
    bad = parse_focus_csv(
        csv("0.1234567890123456789,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD")
    )
    assert reasons(bad) == [(2, "too_many_decimals", "BilledCost")]
    ok = parse_focus_csv(
        csv("0.1234567890000000000000,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD")
    )
    assert ok.rejects == [] and ok.rows[0].values["billed_cost"] == Decimal("0.123456789")


def test_bad_tags_and_optional_values_are_rejected():
    head = HEAD + ",Tags,ConsumedQuantity"
    r = parse_focus_csv(csv(OK + ",not json,1", OK + ',"[1,2]",1', OK + ',"{}",abc', head=head))
    assert reasons(r) == [
        (2, "bad_json", "Tags"),
        (3, "json_not_an_object", "Tags"),
        (4, "not_a_number", "ConsumedQuantity"),
    ]


def test_row_with_the_wrong_number_of_cells_is_rejected():
    r = parse_focus_csv(csv(OK, OK + ",extra", "1,2"))
    assert len(r.rows) == 1 and [x[1] for x in reasons(r)] == ["column_count", "column_count"]


def test_bom_crlf_blank_lines_and_gzip_are_handled():
    raw = b"\xef\xbb\xbf" + (HEAD + "\r\n" + OK + "\r\n\r\n" + OK + "\r\n").encode()
    assert len(parse_focus_csv(raw).rows) == 2
    assert len(parse_focus_csv(gzip.compress(csv(OK, OK))).rows) == 2


def test_size_limits_cover_compressed_and_decompressed_data():
    with pytest.raises(FileError, match="larger"):
        parse_focus_csv(csv(OK), max_bytes=10)
    bomb = gzip.compress(b"x" * 10_000)
    assert len(bomb) < 200
    with pytest.raises(FileError, match="decompressed"):
        parse_focus_csv(bomb, max_bytes=5_000)
    with pytest.raises(FileError, match="corrupt"):
        parse_focus_csv(b"\x1f\x8b" + b"not gzip")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff\xfe\xfa",
    ],
)
def test_empty_and_undecodable_files_are_refused(raw):
    with pytest.raises(FileError):
        parse_focus_csv(raw)


def test_duplicate_headers_and_unknown_declared_versions_are_refused():
    with pytest.raises(FileError, match="duplicate"):
        parse_focus_csv(csv(OK + ",1", head=HEAD + ",BilledCost"))
    with pytest.raises(FileError, match="version"):
        parse_focus_csv(csv(OK), declared_version="9.9")


def test_legacy_provider_name_is_mapped_and_the_mapping_is_recorded():
    head = HEAD + ",ProviderName"
    r = parse_focus_csv(csv(OK + ",Acme Cloud", head=head), declared_version="1.0")
    assert r.aliases_used == {"ProviderName": "ServiceProviderName"}
    assert r.rows[0].values["service_provider_name"] == "Acme Cloud"
    assert r.rows[0].extensions == {"_alias:ProviderName": "ServiceProviderName"}
    both = parse_focus_csv(csv(OK + ",New,Old", head=HEAD + ",ServiceProviderName,ProviderName"))
    assert both.aliases_used == {} and both.rows[0].values["service_provider_name"] == "New"


def test_the_parser_is_deterministic():
    a, b = parse_focus_csv(csv(OK, OK)), parse_focus_csv(csv(OK, OK))
    assert [x.values for x in a.rows] == [x.values for x in b.rows]


def test_purchase_and_usage_lines_keep_billed_and_effective_cost_separate():
    """FOCUS: a commitment purchase has BilledCost > 0 and EffectiveCost 0; the usage it covers carries the
    amortized EffectiveCost. Both measures must survive parsing untouched."""
    purchase = "1000,0,1000,1000,Purchase,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD"
    usage = "0,100,100,100,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD"
    r = parse_focus_csv(csv(purchase, usage))
    p, u = (x.values for x in r.rows)
    assert (p["billed_cost"], p["effective_cost"]) == (1000, 0)
    assert (u["billed_cost"], u["effective_cost"]) == (0, 100)


# ---- FOCUS 1.5 readiness (working draft, ratification scheduled 3 December 2026) ----------------------


def test_version_1_5_can_be_declared_ahead_of_ratification():
    r = parse_focus_csv(
        csv(OK + ",Acme", head=HEAD + ",ServiceProviderName"), declared_version="1.5"
    )
    assert r.declared_version == "1.5"


def test_pricing_currency_may_hold_a_provider_unit_but_billing_currency_stays_a_currency_code():
    head = HEAD + ",PricingCurrency,ServiceProviderName"
    credits = parse_focus_csv(csv(OK + ",PLATFORM-CREDITS,Acme", head=head), declared_version="1.5")
    assert (
        credits.rejects == [] and credits.rows[0].values["pricing_currency"] == "PLATFORM-CREDITS"
    )
    assert reasons(parse_focus_csv(csv(OK + ",has space,Acme", head=head))) == [
        (2, "bad_currency", "PricingCurrency")
    ]
    assert reasons(parse_focus_csv(csv(OK + "," + "X" * 17 + ",Acme", head=head))) == [
        (2, "bad_currency", "PricingCurrency")
    ]
    bad_billing = "1,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,CREDITS"
    assert reasons(parse_focus_csv(csv(bad_billing))) == [(2, "bad_currency", "BillingCurrency")]


def test_identity_columns_are_not_stored_by_default_but_are_reported_as_dropped():
    head = HEAD + ",ServiceProviderName,PrincipalId,CredentialId,RequesterDetails,x_Other"
    row = OK + ',Acme,user-123,key-9,"[{""name"": ""Ann""}]",kept'
    r = parse_focus_csv(csv(row, head=head), declared_version="1.5")
    assert r.rows[0].extensions == {"x_Other": "kept"}  # nothing identifying survives normalization
    assert r.dropped_identity_columns == ["PrincipalId", "CredentialId", "RequesterDetails"]
    assert "PrincipalId" not in r.unknown_columns


def test_identity_columns_can_be_kept_only_by_explicit_choice():
    head = HEAD + ",PrincipalId"
    r = parse_focus_csv(csv(OK + ",user-123", head=head), keep_identity_columns=True)
    assert r.rows[0].extensions == {"PrincipalId": "user-123"} and r.dropped_identity_columns == []


def test_provider_name_alias_is_confirmed_and_publisher_name_is_not_mapped():
    head = HEAD + ",ProviderName,PublisherName"
    r = parse_focus_csv(csv(OK + ",Acme,Publisher Inc", head=head), declared_version="1.2")
    assert r.rows[0].values["service_provider_name"] == "Acme"
    assert (
        r.rows[0].extensions["PublisherName"] == "Publisher Inc"
    )  # preserved, never guessed into another column


def test_service_provider_name_is_mandatory_for_declared_1_4_and_1_5_only():
    with pytest.raises(FileError, match="ServiceProviderName"):
        parse_focus_csv(csv(OK), declared_version="1.4")
    with pytest.raises(FileError, match="ServiceProviderName"):
        parse_focus_csv(csv(OK), declared_version="1.5")
    assert parse_focus_csv(csv(OK), declared_version="1.2").rows  # older exports do not have it
    assert parse_focus_csv(csv(OK), declared_version="unknown").rows
    ok = parse_focus_csv(
        csv(OK + ",Acme", head=HEAD + ",ServiceProviderName"), declared_version="1.4"
    )
    assert ok.rows[0].values["service_provider_name"] == "Acme"
    legacy = parse_focus_csv(csv(OK + ",Acme", head=HEAD + ",ProviderName"), declared_version="1.4")
    assert (
        legacy.rows
    )  # a ProviderName column is mapped, so the file still satisfies the requirement


def test_provider_split_allocation_columns_are_typed_and_json_columns_parse():
    head = (
        HEAD
        + ",AllocatedMethodId,AllocatedResourceId,AllocatedResourceName,AllocatedMethodDetails,AllocatedTags"
    )
    row = (
        OK
        + ',split-v1,pod-7,checkout,"{""Elements"": [{""AllocatedRatio"": 0.25}]}","{""team"": ""pay""}"'
    )
    r = parse_focus_csv(csv(row, head=head), declared_version="1.3")
    v = r.rows[0].values
    assert v["allocated_method_id"] == "split-v1" and v["allocated_resource_id"] == "pod-7"
    assert v["allocated_method_details"] == {"Elements": [{"AllocatedRatio": 0.25}]}
    assert v["allocated_tags"] == {"team": "pay"} and r.rows[0].extensions == {}
