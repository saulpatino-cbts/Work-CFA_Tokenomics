"""Reconciliation rules. All values are SYNTHETIC TEST DATA, not measured provider usage."""

from datetime import UTC, datetime

import pytest

from cfa_tokenomics.usage.models import AggregateObservation, RequestObservation
from cfa_tokenomics.usage.reconcile import Status, app_sum, reconcile

T = datetime(2026, 1, 1, tzinfo=UTC)


def req(i, **kw):
    return RequestObservation("bedrock", "acct", f"r{i}", 1, "model-x", T, **kw)


def test_app_only_has_no_provider_total():
    r = reconcile("input", [req(1, input=10), req(2, input=5)], None)
    assert (r.status, r.app_observed, r.total, r.unattributed) == (Status.APP_ONLY, 15, 15.0, None)


def test_provider_only_has_no_request_detail():
    r = reconcile("input", [], 100.0)
    assert (r.status, r.app_observed, r.total) == (Status.PROVIDER_ONLY, None, 100.0)


def test_reconciled_never_adds_sources():
    r = reconcile("input", [req(1, input=30)], 100.0)
    assert r.status is Status.RECONCILED
    assert r.total == 100.0  # not 130
    assert r.unattributed == 70.0


def test_app_exceeding_provider_is_flagged_not_added():
    r = reconcile("input", [req(1, input=120)], 100.0)
    assert r.status is Status.APP_EXCEEDS_PROVIDER
    assert r.total == 120.0 and r.unattributed is None


def test_unknown_is_not_zero():
    r = reconcile("reasoning", [req(1, input=5)], None)
    assert r.status is Status.UNKNOWN and r.total is None


def test_missing_category_on_some_rows_is_partial_and_withholds_gap():
    r = reconcile("input", [req(1, input=10), req(2)], 100.0)
    assert r.partial and r.app_observed == 10 and r.unattributed is None


def test_zero_is_distinct_from_unknown():
    assert app_sum([req(1, input=0)], "input") == (0, False)
    assert app_sum([req(1)], "input") == (None, False)


def test_retries_are_preserved_as_separate_attempts():
    a = RequestObservation("bedrock", "a", "r1", 1, "m", T, input=10)
    b = RequestObservation("bedrock", "a", "r1", 2, "m", T, input=10)
    assert a.source_key != b.source_key
    assert reconcile("input", [a, b], None).total == 20.0


def test_categories_are_not_summed_together():
    r = reconcile("total", [req(1, input=10, output=5, total=15)], None)
    assert r.total == 15.0  # provider-reported total, not recomputed from parts


def test_aggregate_validation():
    with pytest.raises(ValueError):
        AggregateObservation("bedrock", "a", "m", "bogus", T, T.replace(hour=1), "Sum", 1.0)
    with pytest.raises(ValueError):
        AggregateObservation("bedrock", "a", "m", "input", T, T, "Sum", 1.0)
