"""Cost-export connectors without a database: layouts, configuration, reading runs, store adapters.
All keys, files and figures are SYNTHETIC and the layouts are taken from documentation, not a real export."""

import gzip
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from botocore.config import Config
from botocore.stub import Stubber

from cfa_tokenomics.connectors import costexport as cx
from cfa_tokenomics.connectors import layouts as L
from cfa_tokenomics.connectors.store import (
    AzureBlobStore,
    ObjectInfo,
    S3Store,
    StoreError,
    TooLarge,
)

NOW = datetime(2026, 2, 10, 12, tzinfo=UTC)
OLD = NOW - timedelta(hours=5)


def obj(key, size=10, etag="e", modified=OLD):
    return ObjectInfo(key, size, etag, modified)


class FakeStore:
    def __init__(self, files: dict[str, bytes], modified=OLD):
        self.files, self.modified = files, modified
        self.reads: list[str] = []

    def list(self, prefix):
        for k, v in self.files.items():
            if k.startswith(prefix):
                yield obj(k, len(v), f"etag-{hash(v) & 0xFFFF}", self.modified)

    def read(self, key, limit):
        self.reads.append(key)
        if len(self.files[key]) > limit:
            raise TooLarge(key)
        return self.files[key]


def aws_cfg(**kw):
    return cx.parse_scope("aws", {"bucket": "my-exports", "prefix": "cur/focus", **kw})


def azure_cfg(**kw):
    scope = {
        "account_url": "https://acct.blob.core.windows.net",
        "container": "exports",
        "prefix": "ea/focus",
        **kw,
    }
    return cx.parse_scope("azure", scope)


# ---- configuration: no place for a secret ------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        {"bucket": "b1", "prefix": "p"},  # bucket name too short
        {"bucket": "my-exports", "access_key": "x"},  # credentials have nowhere to go
        {"bucket": "my-exports", "secret": "x"},
        {"bucket": "my-exports", "prefix": "../other"},
        {"bucket": "my-exports", "region": "mars"},
        {"bucket": "my-exports", "focus_version": "9.9"},
        {"bucket": "my-exports", "lookback_periods": 0},
        {"bucket": "my-exports", "lookback_periods": True},
        {"bucket": "my-exports", "max_run_mb": 10_000},
        {"bucket": "my-exports", "allow_partial": "yes"},
    ],
)
def test_aws_scope_rejects_bad_or_secret_settings(scope):
    with pytest.raises(cx.ConfigError):
        cx.parse_scope("aws", scope)


@pytest.mark.parametrize(
    "scope",
    [
        {"account_url": "http://acct.blob.core.windows.net", "container": "exports"},  # not https
        {
            "account_url": "https://acct.blob.core.windows.net/?sv=2024&sig=abc",
            "container": "exports",
        },  # a SAS token
        {"account_url": "https://user:pw@acct.blob.core.windows.net", "container": "exports"},
        {"account_url": "https://evil.example.com", "container": "exports"},
        {
            "account_url": "https://acct.blob.core.windows.net/exports",
            "container": "exports",
        },  # a path
        {"account_url": "https://acct.blob.core.windows.net", "container": "Exports"},
        {
            "account_url": "https://acct.blob.core.windows.net",
            "container": "exports",
            "connection_string": "x",
        },
        {
            "account_url": "https://acct.blob.core.windows.net",
            "container": "exports",
            "sas_token": "x",
        },
    ],
)
def test_azure_scope_rejects_sas_tokens_credentials_and_foreign_hosts(scope):
    with pytest.raises(cx.ConfigError):
        cx.parse_scope("azure", scope)


def test_valid_scopes_normalize_and_default():
    a = aws_cfg()
    assert (a.lookback_periods, a.settle_minutes, a.max_run_mb, a.focus_version) == (
        3,
        30,
        200,
        "1.2",
    )
    assert a.location == "s3://my-exports/cur/focus"
    z = azure_cfg(prefix="/ea/focus/")
    assert z.prefix == "ea/focus" and z.account_url == "https://acct.blob.core.windows.net"
    with pytest.raises(cx.ConfigError):
        cx.parse_scope("gcp", {})


# ---- layouts -----------------------------------------------------------------------------------


def test_azure_runs_group_by_period_and_run_and_ignore_manifests():
    objs = [
        obj("ea/focus/20260101-20260131/run-a/part_0001.csv.gz"),
        obj("ea/focus/20260101-20260131/run-a/part_0002.csv.gz"),
        obj("ea/focus/20260101-20260131/run-a/manifest.json"),
        obj("ea/focus/20260101-20260131/run-b/part_0001.csv.gz", modified=NOW - timedelta(hours=2)),
        obj("ea/focus/20260101-20260131/run-b/manifest.json"),
        obj("ea/focus/not-a-period/run/part.csv.gz"),
        obj("other/20260101-20260131/run/part.csv.gz"),
    ]
    runs = L.azure_runs(objs, "ea/focus")
    assert sorted((r.period, r.run_id, len(r.parts)) for r in runs) == [
        ("20260101-20260131", "run-a", 2),
        ("20260101-20260131", "run-b", 1),
    ]
    chosen, passed = L.latest_per_period(runs)
    assert [r.run_id for r in chosen] == [
        "run-b"
    ] and passed == 1  # the newest run replaces the older one


def test_aws_runs_handle_overwrite_and_create_new_delivery_and_skip_metadata():
    objs = [
        obj(
            "cur/focus/data/BILLING_PERIOD=2026-01/export-00001.csv.gz"
        ),  # overwrite: files in place
        obj("cur/focus/data/BILLING_PERIOD=2026-01/export-00002.csv.gz"),
        obj(
            "cur/focus/data/BILLING_PERIOD=2026-02/20260210T0000Z-abc/export-00001.csv.gz"
        ),  # create-new
        obj("cur/focus/metadata/BILLING_PERIOD=2026-02/export-Manifest.json"),
        obj("cur/focus/data/BILLING_PERIOD=2026-02/20260210T0000Z-abc/export-00001.parquet"),
    ]
    runs = L.aws_runs(objs, "cur/focus")
    by = {(r.period, r.run_id): r for r in runs}
    assert set(by) == {("2026-01", ""), ("2026-02", "20260210T0000Z-abc")}
    assert len(by[("2026-01", "")].parts) == 2
    assert by[("2026-02", "20260210T0000Z-abc")].unsupported == ("parquet",)
    assert by[("2026-01", "")].period_end.isoformat() == "2026-01-31"


def test_the_fingerprint_changes_when_a_part_is_replaced_in_place():
    a = L.azure_runs([obj("p/20260101-20260131/r/x.csv.gz", etag="v1")], "p")[0]
    b = L.azure_runs([obj("p/20260101-20260131/r/x.csv.gz", etag="v2")], "p")[0]
    c = L.azure_runs([obj("p/20260101-20260131/r/x.csv.gz", etag="v1")], "p")[0]
    assert a.fingerprint != b.fingerprint and a.fingerprint == c.fingerprint


# ---- reading a run -----------------------------------------------------------------------------

H = b"BilledCost,EffectiveCost,ChargeCategory\n"


def run_of(*keys, store=None):
    return SimpleNamespace(parts=tuple(obj(k, len(store.files[k])) for k in keys))


def test_parts_are_joined_into_one_csv_under_one_header():
    files = {
        "a.csv.gz": gzip.compress(H + b"1,1,Usage\n"),
        "b.csv": H + b"2,2,Usage",
        "c.csv.gz": gzip.compress(H),
    }
    st = FakeStore(files)
    out = cx.read_run(st, run_of("a.csv.gz", "b.csv", "c.csv.gz", store=st), 10_000)
    assert out == H + b"1,1,Usage\n2,2,Usage\n"


def test_parts_with_different_columns_are_refused_not_merged():
    st = FakeStore({"a.csv": H + b"1,1,Usage\n", "b.csv": b"BilledCost,ChargeCategory\n1,Usage\n"})
    with pytest.raises(cx.RunError, match="different columns"):
        cx.read_run(st, run_of("a.csv", "b.csv", store=st), 10_000)


def test_a_bom_and_crlf_header_still_match():
    st = FakeStore(
        {
            "a.csv": b"\xef\xbb\xbf" + H.replace(b"\n", b"\r\n") + b"1,1,Usage\r\n",
            "b.csv": H + b"2,2,Usage\n",
        }
    )
    assert cx.read_run(st, run_of("a.csv", "b.csv", store=st), 10_000).count(b"Usage") == 2


def test_oversize_and_gzip_bombs_and_truncation_are_refused():
    big = gzip.compress(H + b"1,1,Usage\n" * 200_000)
    st = FakeStore({"big.csv.gz": big})
    assert len(big) < 100_000
    with pytest.raises(TooLarge):  # small on the wire, large when unpacked
        cx.read_run(st, run_of("big.csv.gz", store=st), 100_000)
    st = FakeStore({"a.csv": H + b"1,1,Usage\n" * 50})
    with pytest.raises(TooLarge):
        cx.read_run(st, run_of("a.csv", store=st), 100)
    cut = gzip.compress(H + b"1,1,Usage\n" * 100)[:-10]
    st = FakeStore({"cut.csv.gz": cut})
    with pytest.raises(cx.RunError, match="truncated"):
        cx.read_run(st, run_of("cut.csv.gz", store=st), 10_000)
    st = FakeStore({"bad.csv.gz": b"not gzip at all"})
    with pytest.raises(cx.RunError, match="not valid gzip"):
        cx.read_run(st, run_of("bad.csv.gz", store=st), 10_000)


def test_concatenated_gzip_members_are_read():
    st = FakeStore({"a.csv.gz": gzip.compress(H + b"1,1,Usage\n") + gzip.compress(b"2,2,Usage\n")})
    assert cx.read_run(st, run_of("a.csv.gz", store=st), 10_000).endswith(b"2,2,Usage\n")


# ---- check and discover ------------------------------------------------------------------------


def test_check_reports_each_layer_on_its_own():
    cfg = azure_cfg()
    empty = FakeStore({})
    steps = cx.check(cfg, empty, NOW)
    assert [(s.name, s.ok) for s in steps] == [
        ("configuration", True),
        ("access", True),
        ("data", False),
    ]
    assert "no export runs found" in steps[-1].message

    parquet = FakeStore({"ea/focus/20260101-20260131/r/x.parquet": b"PAR1"})
    steps = cx.check(cfg, parquet, NOW)
    assert not steps[-1].ok and "CSV" in steps[-1].message

    good = FakeStore({"ea/focus/20260101-20260131/r/x.csv.gz": b"x"})
    steps = cx.check(cfg, good, NOW)
    assert all(s.ok for s in steps) and "1 period(s) ready" in steps[-1].message

    class Denied:
        def list(self, prefix):
            raise StoreError("access_denied", "access was denied")
            yield  # pragma: no cover

    steps = cx.check(cfg, Denied(), NOW)
    assert [(s.name, s.ok) for s in steps] == [("configuration", True), ("access", False)]


def test_discover_ignores_periods_outside_the_lookback():
    files = {f"ea/focus/{p}/r/x.csv.gz": b"x" for p in ("20250101-20250131", "20260101-20260131")}
    d = cx.discover(azure_cfg(lookback_periods=3), FakeStore(files), NOW)
    assert [r.period for r in d.selected] == ["20260101-20260131"]
    assert [r.period for r in d.outside_lookback] == ["20250101-20250131"]


# ---- store adapters ----------------------------------------------------------------------------


def s3_client():
    import boto3

    return boto3.client("s3", region_name="us-east-1", config=Config(retries={"max_attempts": 1}))


def test_s3_store_lists_across_pages_and_reads_with_a_limit():
    c = s3_client()
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with Stubber(c) as st:
        st.add_response(
            "list_objects_v2",
            {
                "IsTruncated": True,
                "NextContinuationToken": "n",
                "Contents": [{"Key": "p/a", "Size": 3, "ETag": '"e1"', "LastModified": t}],
            },
            {"Bucket": "b", "Prefix": "p/"},
        )
        st.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "p/b", "Size": 4, "ETag": '"e2"', "LastModified": t}]},
            {"Bucket": "b", "Prefix": "p/", "ContinuationToken": "n"},
        )
        got = list(S3Store("b", client=c).list("p/"))
    assert [(o.key, o.size, o.etag) for o in got] == [("p/a", 3, "e1"), ("p/b", 4, "e2")]


def test_s3_store_maps_errors_without_leaking_detail():
    c = s3_client()
    with Stubber(c) as st:
        st.add_client_error(
            "list_objects_v2",
            service_error_code="AccessDenied",
            service_message="arn:aws:iam::123:role/secret-name denied",
            http_status_code=403,
        )
        with pytest.raises(StoreError) as e:
            list(S3Store("b", client=c).list("p/"))
    assert (
        e.value.kind == "access_denied"
        and "secret-name" not in str(e.value)
        and "123" not in str(e.value)
    )
    with Stubber(c) as st:
        st.add_client_error(
            "list_objects_v2", service_error_code="NoSuchBucket", http_status_code=404
        )
        with pytest.raises(StoreError) as e:
            list(S3Store("b", client=c).list("p/"))
    assert e.value.kind == "not_found"


def test_s3_store_read_refuses_a_large_object_before_reading_it():
    class Body:
        def read(self, n):  # pragma: no cover - must not be reached
            raise AssertionError("read a body that is over the limit")

    class Client:
        def get_object(self, **kw):
            return {"ContentLength": 500, "Body": Body()}

    with pytest.raises(TooLarge):
        S3Store("b", client=Client()).read("k", 100)


class FakeContainer:
    def __init__(self, blobs, fail=None):
        self.blobs, self.fail = blobs, fail

    def list_blobs(self, name_starts_with=""):
        if self.fail:
            raise self.fail
        t = datetime(2026, 1, 1, tzinfo=UTC)
        for k, v in self.blobs.items():
            if k.startswith(name_starts_with):
                yield SimpleNamespace(name=k, size=len(v), etag='"0x8D"', last_modified=t)

    def download_blob(self, key, offset=0, length=None):
        data = self.blobs[key][offset : offset + length]
        return SimpleNamespace(readall=lambda: data)


def test_azure_store_lists_and_reads_with_a_limit_and_maps_errors():
    store = AzureBlobStore(
        "https://acct.blob.core.windows.net",
        "exports",
        client=FakeContainer({"p/a": b"hello", "q/b": b"x"}),
    )
    assert [(o.key, o.size, o.etag) for o in store.list("p/")] == [("p/a", 5, "0x8D")]
    assert store.read("p/a", 10) == b"hello"
    with pytest.raises(TooLarge):
        store.read("p/a", 3)

    class Forbidden(Exception):
        status_code = 403

    with pytest.raises(StoreError) as e:
        list(
            AzureBlobStore(
                "u", "c", client=FakeContainer({}, fail=Forbidden("https://acct/?sig=SECRET"))
            ).list("p/")
        )
    assert e.value.kind == "access_denied" and "SECRET" not in str(e.value)
