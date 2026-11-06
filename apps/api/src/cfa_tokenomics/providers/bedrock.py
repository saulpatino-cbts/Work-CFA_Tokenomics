"""Amazon Bedrock CloudWatch metric normalization.

Maps ``GetMetricData`` results to aggregate observations. Metric names and semantics must be
verified against the current Bedrock runtime-metrics documentation before live use [VERIFY]:
https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring-runtime-metrics.html

Categories stay as the provider defines them: nothing is summed across categories, and a
period with no datapoint produces no row (unknown, not zero).
"""

from datetime import timedelta

from ..usage.models import AggregateObservation, Quality

NORMALIZATION_VERSION = "bedrock-cw-1"

# CloudWatch metric name -> our category. Verify names against the AWS docs [VERIFY].
METRIC_CATEGORY = {
    "InputTokenCount": "input",
    "OutputTokenCount": "output",
    "CacheReadInputTokenCount": "cache_read",
    "CacheWriteInputTokenCount": "cache_write",
}


class NormalizationError(ValueError):
    pass


def normalize_metric_results(
    account: str,
    model_id: str,
    period_seconds: int,
    results: list[dict],
    statistic: str = "Sum",
) -> tuple[list[AggregateObservation], bool]:
    """Return (observations, complete). ``results[].Id`` must be a METRIC_CATEGORY key.

    ``complete`` is False if CloudWatch reported anything other than ``Complete``.
    """
    if statistic != "Sum":
        raise NormalizationError("only the Sum statistic is token-additive within a window")
    out: list[AggregateObservation] = []
    complete = True
    for r in results:
        metric = r.get("Id")
        if metric not in METRIC_CATEGORY:
            raise NormalizationError(f"unsupported metric id {metric!r}")
        status = r.get("StatusCode", "Complete")
        if status != "Complete":
            complete = False
        times, values = r.get("Timestamps", []), r.get("Values", [])
        if len(times) != len(values):
            raise NormalizationError("timestamps and values differ in length")
        for ts, v in zip(times, values, strict=True):
            if v < 0:
                raise NormalizationError("negative usage value")
            out.append(
                AggregateObservation(
                    provider="bedrock",
                    account=account,
                    model_id=model_id,
                    category=METRIC_CATEGORY[metric],
                    window_start=ts,
                    window_end=ts + timedelta(seconds=period_seconds),
                    statistic=statistic,
                    value=float(v),
                    quality=Quality.REPORTED if status == "Complete" else Quality.PARTIAL,
                    normalization_version=NORMALIZATION_VERSION,
                )
            )
    return out, complete
