"""The export sanitizer. The 'sensitive' values planted below are INVENTED stand-ins shaped like real ones
(emails, ARNs, account numbers, GUIDs, owner names, identity columns); none is real."""

import csv
import gzip
import io
import json
import os
import stat
from decimal import Decimal

import pytest

from cfa_tokenomics.focus.parse import parse_focus_csv
from cfa_tokenomics.sanitize import focus_export as fx

ACCT = "123456789012"
ARN = f"arn:aws:ec2:us-east-1:{ACCT}:instance/i-0abc123def456"
EMAIL = "jane.doe@corp-example.test"
GUID = "0a1b2c3d-1111-4222-8333-444455556666"  # a subscription id: must not survive
SKU_GUID = "9f8e7d6c-aaaa-4bbb-8ccc-ddddeeeeffff"  # a catalog SKU id: public, kept joinable
IP = "10.20.30.40"
PLANTED = [
    ACCT,
    ARN,
    EMAIL,
    GUID,
    IP,
    "Jane Doe",
    "Project Falcon",
    "principal-jane",
    "cred-jane",
    "payroll-prod-db",
    "Falcon Finance",
]
HEADER = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ListUnitPrice", "ConsumedQuantity", "PricingQuantity", "ChargeCategory",
    "ChargeDescription", "ChargePeriodStart", "ChargePeriodEnd", "BillingCurrency", "BillingAccountId", "BillingAccountName", "SubAccountId",
    "ServiceName", "ServiceCategory", "ServiceProviderName", "ConsumedUnit", "PricingUnit", "SkuId", "SkuPriceId", "SkuPriceDetails",
    "ResourceId", "ResourceName", "InvoiceId", "Tags", "PrincipalId", "CredentialId", "RequesterDetails", "x_OwnerName", "x_CostCenterNote",
]  # fmt: skip


def row(cost="12.50", qty="1000", **over):
    r = {
        "BilledCost": cost, "EffectiveCost": cost, "ListCost": cost, "ContractedCost": cost, "ListUnitPrice": "0.0125",
        "ConsumedQuantity": qty, "PricingQuantity": qty, "ChargeCategory": "Usage",
        "ChargeDescription": f"Usage for {EMAIL} on {ARN} at {IP}", "ChargePeriodStart": "2026-10-01T00:00:00Z",
        "ChargePeriodEnd": "2026-10-02T00:00:00Z", "BillingCurrency": "USD", "BillingAccountId": ACCT,
        "BillingAccountName": "Falcon Finance", "SubAccountId": GUID, "ServiceName": f"Service {ACCT}",
        "ServiceCategory": "AI and Machine Learning", "ServiceProviderName": "Amazon Web Services", "ConsumedUnit": "Tokens",
        "PricingUnit": "1000 Tokens", "SkuId": SKU_GUID, "SkuPriceId": f"{SKU_GUID}-p",
        "SkuPriceDetails": json.dumps({"ModelId": "model-a", "Owner": EMAIL, "TokenDirection": "Input"}),
        "ResourceId": ARN, "ResourceName": "payroll-prod-db", "InvoiceId": "INV-998877",
        "Tags": json.dumps({"app": "claims-assistant", "owner": EMAIL, "Project Falcon": "x", "env": "prod"}),
        "PrincipalId": "principal-jane", "CredentialId": "cred-jane", "RequesterDetails": json.dumps([{"Id": "Jane Doe"}]),
        "x_OwnerName": "Jane Doe", "x_CostCenterNote": "Project Falcon",
    }  # fmt: skip
    r.update(over)
    return r


def write(path, rows, gz=False, header=HEADER):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=header, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    data = out.getvalue().encode()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(gzip.compress(data) if gz else data)


def read(path):
    raw = open(path, "rb").read()
    text = gzip.decompress(raw).decode() if path.endswith(".gz") else raw.decode()
    return text, list(csv.DictReader(io.StringIO(text)))


def run(tmp_path, rows=None, gz=False, **opt):
    src = tmp_path / "in" / ("export.csv.gz" if gz else "export.csv")
    write(
        str(src),
        rows or [row(), row(cost="3.20", BillingAccountId="999988887777", ResourceId=ARN + "-2")],
        gz,
    )
    out = tmp_path / "out" / src.name
    opts = fx.Options(salt=opt.pop("salt", b"s" * 32), **opt)
    rep = fx.sanitize_tree(str(src), str(out), opts)
    return str(out), rep


def test_nothing_planted_survives_in_the_output_or_the_report(tmp_path):
    out, rep = run(tmp_path, keep_tag_values_for=frozenset({"app", "env"}))
    text, _ = read(out)
    blob = text + json.dumps(rep)
    for needle in PLANTED:
        assert needle not in blob, needle
    assert "999988887777" not in blob and "INV-998877" not in blob


def test_only_allow_listed_columns_pass_everything_else_is_dropped_and_named_in_the_report(
    tmp_path,
):
    out, rep = run(tmp_path)
    _, rows = read(out)
    cols = set(rows[0])
    assert {
        "BilledCost",
        "ChargeCategory",
        "ServiceName",
        "SkuId",
        "Tags",
        "BillingAccountId",
        "ResourceId",
    } <= cols
    for gone in (
        "ChargeDescription",
        "PrincipalId",
        "CredentialId",
        "RequesterDetails",
        "x_OwnerName",
        "x_CostCenterNote",
    ):
        assert gone not in cols
    f = rep["files"][0]
    assert {"ChargeDescription", "PrincipalId", "x_OwnerName", "RequesterDetails"} <= set(
        f["dropped"]
    )
    assert "BillingAccountId" in f["pseudonymized"] and "BilledCost" in f["kept"]


def test_the_owner_can_keep_an_extra_column_but_patterns_inside_it_are_still_scrubbed(tmp_path):
    out, _ = run(
        tmp_path,
        rows=[row(x_CostCenterNote=f"approved by {EMAIL} for the team")],
        allow_columns=frozenset({"x_CostCenterNote"}),
    )
    _, rows = read(out)
    assert (
        "x_CostCenterNote" in rows[0] and "approved by" in rows[0]["x_CostCenterNote"]
    )  # kept on the owner's say-so
    assert EMAIL not in rows[0]["x_CostCenterNote"]  # but an email in it is still replaced
    assert "x_OwnerName" not in rows[0]  # the other extension column stays dropped
    # The scrubber finds patterns, not names: that is why free-text columns are dropped by default.


def test_identifiers_become_consistent_pseudonyms_within_a_run_and_differ_across_salts(tmp_path):
    out, _ = run(tmp_path)
    _, rows = read(out)
    a, b = rows
    assert a["BillingAccountId"] != b["BillingAccountId"] and a["BillingAccountId"].startswith(
        "acct-"
    )
    assert a["ResourceId"].startswith("res-") and a["ResourceId"] != b["ResourceId"]
    twin = [row(), row()]
    out2, _ = run(tmp_path / "again", rows=twin)
    _, same = read(out2)
    assert (
        same[0]["BillingAccountId"] == same[1]["BillingAccountId"]
        and same[0]["ResourceId"] == same[1]["ResourceId"]
    )
    out3, _ = run(tmp_path / "other", rows=twin, salt=b"t" * 32)
    assert read(out3)[1][0]["BillingAccountId"] != same[0]["BillingAccountId"]


def test_costs_and_quantities_are_unchanged_without_a_scale(tmp_path):
    out, _ = run(tmp_path)
    _, rows = read(out)
    assert (
        rows[0]["BilledCost"] == "12.50"
        and rows[0]["ConsumedQuantity"] == "1000"
        and rows[0]["ListUnitPrice"] == "0.0125"
    )
    assert (
        rows[0]["ChargePeriodStart"] == "2026-10-01T00:00:00Z"
        and rows[0]["ChargeCategory"] == "Usage"
    )


def test_a_scale_multiplies_cost_and_quantity_exactly_and_leaves_unit_prices_and_hides_the_factor(
    tmp_path,
):
    out, rep = run(tmp_path, scale=Decimal("0.37"))
    _, rows = read(out)
    assert Decimal(rows[0]["BilledCost"]) == Decimal("12.50") * Decimal("0.37") == Decimal("4.625")
    assert (
        Decimal(rows[0]["ConsumedQuantity"]) == Decimal("370")
        and rows[0]["ListUnitPrice"] == "0.0125"
    )
    assert rep["files"][0]["scaled"] is True and "0.37" not in json.dumps(rep)
    tiny = run(tmp_path / "t", rows=[row(cost="0.000000000000000003")], scale=Decimal("0.5"))[
        0
    ]  # 1.5e-18 rounds half-even to 2e-18
    assert (
        len(read(tiny)[1][0]["BilledCost"].split(".")[1]) == 18
    )  # quantized to the 18 places the importer allows


def test_text_inside_kept_columns_is_scrubbed_but_catalog_ids_are_not(tmp_path):
    out, rep = run(tmp_path)
    _, rows = read(out)
    r = rows[0]
    assert (
        EMAIL not in r["SkuPriceDetails"]
        and "model-a" in r["SkuPriceDetails"]
        and "TokenDirection" in r["SkuPriceDetails"]
    )
    assert ACCT not in r["ServiceName"] and r["ServiceName"].startswith("Service ")
    assert (
        r["SkuId"] == SKU_GUID and r["SkuPriceId"] == f"{SKU_GUID}-p"
    )  # public catalog identifiers stay joinable
    assert (
        rep["files"][0]["scrubbed"]["email"] >= 1 and rep["files"][0]["scrubbed"]["account12"] >= 1
    )


def test_tags_keep_simple_keys_pseudonymize_values_unless_asked_and_drop_what_cannot_be_read(
    tmp_path,
):
    out, _ = run(tmp_path)
    _, rows = read(out)
    t = json.loads(rows[0]["Tags"])
    assert (
        "app" in t and t["app"].startswith("tagval-") and "claims-assistant" not in rows[0]["Tags"]
    )
    assert any(k.startswith("tagkey-") for k in t)  # a key with a space and capitals is not kept
    assert "Project Falcon" not in rows[0]["Tags"] and "owner" in t and EMAIL not in rows[0]["Tags"]
    out2, _ = run(tmp_path / "keep", keep_tag_values_for=frozenset({"app", "env"}))
    t2 = json.loads(read(out2)[1][0]["Tags"])
    assert (
        t2["app"] == "claims-assistant"
        and t2["env"] == "prod"
        and t2["owner"].startswith("tagval-")
    )
    bad, _ = run(tmp_path / "bad", rows=[row(Tags="{not json"), row(Tags='["a"]')])
    assert [r["Tags"] for r in read(bad)[1]] == ["", ""]


def test_a_leak_found_at_the_end_deletes_the_output_and_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(fx.Sanitizer, "scrub", lambda self, text, counts: text)  # a broken scrubber
    src = tmp_path / "in" / "e.csv"
    write(str(src), [row()])
    out = tmp_path / "out" / "e.csv"
    with pytest.raises(fx.SanitizeError, match="survived"):
        fx.sanitize_tree(
            str(src),
            str(out),
            fx.Options(b"s" * 32, allow_columns=frozenset({"ChargeDescription"})),
        )
    assert not out.exists()


def test_a_tree_keeps_its_layout_skips_non_csv_and_is_all_or_nothing(tmp_path):
    base = tmp_path / "in" / "cur" / "focus" / "data" / "BILLING_PERIOD=2026-10"
    write(str(base / "export-00001.csv.gz"), [row()], gz=True)
    write(str(base / "export-00002.csv.gz"), [row(cost="1")], gz=True)
    (base / "Manifest.json").write_text("{}")
    out = tmp_path / "out"
    rep = fx.sanitize_tree(str(tmp_path / "in"), str(out), fx.Options(b"s" * 32))
    got = sorted(os.path.relpath(os.path.join(r, n), out) for r, _d, ns in os.walk(out) for n in ns)
    assert (
        "cur/focus/data/BILLING_PERIOD=2026-10/export-00001.csv.gz" in got
        and "sanitize-report.json" in got
    )
    assert rep["skipped_not_csv"] == ["cur/focus/data/BILLING_PERIOD=2026-10/Manifest.json"]
    assert not any(n.endswith("Manifest.json") for n in got)
    a = read(str(out / "cur/focus/data/BILLING_PERIOD=2026-10/export-00001.csv.gz"))[1][0][
        "BillingAccountId"
    ]
    b = read(str(out / "cur/focus/data/BILLING_PERIOD=2026-10/export-00002.csv.gz"))[1][0][
        "BillingAccountId"
    ]
    assert a == b  # one run, one salt: the same account is the same pseudonym in every part
    with pytest.raises(fx.SanitizeError, match="not empty"):
        fx.sanitize_tree(str(tmp_path / "in"), str(out), fx.Options(b"s" * 32))
    broken = tmp_path / "in2"
    write(str(broken / "a.csv"), [row()])
    (broken / "b.csv").write_text("A,B\n1,2,3\n")  # a row with too many cells
    with pytest.raises(fx.SanitizeError):
        fx.sanitize_tree(str(broken), str(tmp_path / "out2"), fx.Options(b"s" * 32))
    assert not (tmp_path / "out2" / "a.csv").exists()  # the good file was not left behind
    with pytest.raises(fx.SanitizeError, match="no CSV"):
        fx.sanitize_tree(
            str(tmp_path / "empty"), str(tmp_path / "o3"), fx.Options(b"s" * 32)
        ) if os.makedirs(tmp_path / "empty") is None else None


def test_gzip_in_gives_gzip_out_and_a_weak_salt_is_refused(tmp_path):
    out, _ = run(tmp_path, gz=True)
    assert open(out, "rb").read(2) == b"\x1f\x8b"
    with pytest.raises(fx.SanitizeError):
        fx.Sanitizer(fx.Options(b"short"))


def test_the_sanitized_file_still_imports_cleanly_and_keeps_its_grouping(tmp_path):
    out, _ = run(
        tmp_path,
        rows=[
            row(),
            row(cost="3.20", ResourceId=ARN + "-2"),
            row(cost="1.00", BillingAccountId="999988887777"),
        ],
        keep_tag_values_for=frozenset({"app"}),
    )
    text, rows = read(out)
    parsed = parse_focus_csv(text.encode(), "1.2", 10_000_000)
    assert len(parsed.rows) == 3 and not parsed.rejects
    assert len({r["BillingAccountId"] for r in rows}) == 2  # two accounts in, two pseudonyms out
    assert (
        parsed.rows[0].values["tags"]["app"] == "claims-assistant"
    )  # allocation by tag keeps working


def test_the_command_reports_without_values_creates_a_private_salt_file_and_refuses_bad_input(
    tmp_path, capsys
):
    src = tmp_path / "in" / "e.csv"
    write(str(src), [row()])
    salt = tmp_path / "salt.bin"
    assert (
        fx.main([str(src), str(tmp_path / "out.csv"), "--salt-file", str(salt), "--scale", "0.5"])
        == 0
    )
    said = capsys.readouterr().out
    assert (
        "created a salt file" in said and "0.5" not in said and salt.read_bytes().hex() not in said
    )
    assert stat.S_IMODE(os.stat(salt).st_mode) == 0o600 and len(salt.read_bytes()) == 32
    first = read(str(tmp_path / "out.csv"))[1][0]["BillingAccountId"]
    assert (
        fx.main([str(src), str(tmp_path / "out2.csv"), "--salt-file", str(salt)]) == 0
    )  # the salt is reused
    assert read(str(tmp_path / "out2.csv"))[1][0]["BillingAccountId"] == first
    capsys.readouterr()
    assert (
        fx.main([str(src), str(tmp_path / "out.csv")]) == 1
        and "not empty" in capsys.readouterr().err
    )
    assert fx.main([str(src), str(tmp_path / "x.csv"), "--scale", "-1"]) == 1
    assert fx.main([str(src), str(tmp_path / "y.csv"), "--scale", "abc"]) == 1
    assert fx.main([]) == 2 and fx.main(["only-one"]) == 2
    assert fx.main([str(tmp_path / "missing.csv"), str(tmp_path / "z.csv")]) == 1
