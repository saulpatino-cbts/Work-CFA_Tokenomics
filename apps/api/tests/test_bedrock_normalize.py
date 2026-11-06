"""Bedrock normalization. Fixtures are SYNTHETIC and shaped like CloudWatch GetMetricData output."""

from datetime import UTC, datetime, timedelta

import pytest

from cfa_tokenomics.providers.bedrock import NormalizationError, normalize_metric_results
from cfa_tokenomics.usage.models import Quality

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def result(metric, values, status="Complete"):
    times = [T0 + timedelta(minutes=5 * i) for i in range(len(values))]
    return {"Id": metric, "StatusCode": status, "Timestamps": times, "Values": values}


def test_maps_categories_and_windows():
    obs, complete = normalize_metric_results(
        "acct",
        "model-x",
        300,
        [result("InputTokenCount", [10, 20]), result("OutputTokenCount", [3])],
    )
    assert complete
    assert [(o.category, o.value) for o in obs] == [
        ("input", 10.0),
        ("input", 20.0),
        ("output", 3.0),
    ]
    assert obs[0].window_end - obs[0].window_start == timedelta(seconds=300)
    assert all(o.provider == "bedrock" and o.quality is Quality.REPORTED for o in obs)


def test_cache_categories_stay_separate():
    obs, _ = normalize_metric_results(
        "a",
        "m",
        300,
        [result("CacheReadInputTokenCount", [7]), result("CacheWriteInputTokenCount", [2])],
    )
    assert {o.category for o in obs} == {"cache_read", "cache_write"}


def test_missing_period_makes_no_row_rather_than_zero():
    obs, _ = normalize_metric_results("a", "m", 300, [result("InputTokenCount", [])])
    assert obs == []


def test_partial_data_is_flagged_and_incomplete():
    obs, complete = normalize_metric_results(
        "a", "m", 300, [result("InputTokenCount", [5], status="PartialData")]
    )
    assert not complete and obs[0].quality is Quality.PARTIAL


@pytest.mark.parametrize(
    "bad",
    [
        [result("SomethingElse", [1])],
        [result("InputTokenCount", [-1])],
        [{"Id": "InputTokenCount", "Timestamps": [T0], "Values": []}],
    ],
)
def test_malformed_input_is_rejected(bad):
    with pytest.raises(NormalizationError):
        normalize_metric_results("a", "m", 300, bad)


def test_only_sum_statistic_accepted():
    with pytest.raises(NormalizationError):
        normalize_metric_results("a", "m", 300, [], statistic="Average")
