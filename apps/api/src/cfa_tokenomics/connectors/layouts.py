"""How each cloud lays an export out in storage, and which run of it to import.

An export run is a set of files that together hold one billing period's data. Both clouds split a
large export into several files, so a run must be imported as one logical file: importing the parts
one at a time would make each part supersede the last for the same account and window.

The layouts below come from vendor documentation and have NOT been checked against a real export.
Matching is deliberately tolerant (it looks for the documented date folder, not an exact depth), and
nothing here depends on a manifest's internal fields, which were not verified.

Azure:  <prefix>/<YYYYMMDD-YYYYMMDD>/<run id>/<part files and manifest.json>
AWS:    <prefix>/data/BILLING_PERIOD=<YYYY-MM>/[<timestamp>-<execution id>/]<part files>
        (overwrite delivery writes the files straight into the partition; create-new adds a run folder)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .store import ObjectInfo

_AZURE_PERIOD = re.compile(r"^(\d{8})-(\d{8})$")
_AWS_PERIOD = re.compile(r"^BILLING_PERIOD=(\d{4})-(\d{2})$")


def classify(key: str) -> str:
    """csv, gz (gzip CSV), unsupported:<why>, or ignore (manifests and anything else)."""
    k = key.lower()
    if k.endswith(".csv"):
        return "csv"
    if k.endswith(".csv.gz") or k.endswith(".gz"):
        return "gz"
    if k.endswith(".parquet"):
        return "unsupported:parquet"
    if k.endswith(".zip"):
        return "unsupported:zip"
    return "ignore"


@dataclass(frozen=True)
class Run:
    provider: str
    period: str
    run_id: str
    period_end: date
    parts: tuple[ObjectInfo, ...]
    unsupported: tuple[str, ...]
    newest: datetime

    @property
    def fingerprint(self) -> str:
        """Changes when any part is replaced (a different etag or size), so an overwritten export is
        seen as new while an untouched one is not downloaded again."""
        raw = "|".join(
            f"{p.key}:{p.etag}:{p.size}" for p in sorted(self.parts, key=lambda p: p.key)
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _rel(key: str, prefix: str) -> list[str] | None:
    base = prefix.strip("/")
    if base and not (key == base or key.startswith(base + "/")):
        return None
    rest = key[len(base) :].lstrip("/")
    return rest.split("/") if rest else None


def _group(provider: str, found: dict[tuple[str, str], dict]) -> list[Run]:
    runs = []
    for (period, run_id), g in found.items():
        if not g["parts"] and not g["unsupported"]:
            continue
        runs.append(
            Run(
                provider,
                period,
                run_id,
                g["end"],
                tuple(sorted(g["parts"], key=lambda p: p.key)),
                tuple(sorted(set(g["unsupported"]))),
                g["newest"],
            )  # fmt: skip
        )
    return runs


def azure_runs(objects: list[ObjectInfo], prefix: str) -> list[Run]:
    found: dict[tuple[str, str], dict] = {}
    for o in objects:
        segs = _rel(o.key, prefix)
        if not segs or len(segs) < 3:
            continue
        m = _AZURE_PERIOD.match(segs[0])
        if not m:
            continue
        try:
            end = datetime.strptime(m.group(2), "%Y%m%d").replace(tzinfo=UTC).date()
        except ValueError:
            continue
        g = found.setdefault(
            (segs[0], segs[1]), {"parts": [], "unsupported": [], "end": end, "newest": o.modified}
        )
        g["newest"] = max(g["newest"], o.modified)
        kind = classify(o.key)
        if kind in ("csv", "gz"):
            g["parts"].append(o)
        elif kind.startswith("unsupported:"):
            g["unsupported"].append(kind.split(":", 1)[1])
    return _group("azure", found)


def aws_runs(objects: list[ObjectInfo], prefix: str) -> list[Run]:
    found: dict[tuple[str, str], dict] = {}
    for o in objects:
        segs = _rel(o.key, prefix)
        if not segs or "metadata" in segs[:-1]:
            continue
        idx = next((i for i, s in enumerate(segs) if _AWS_PERIOD.match(s)), None)
        if idx is None or idx == 0 or segs[idx - 1] != "data":
            continue
        m = _AWS_PERIOD.match(segs[idx])
        assert m
        tail = segs[idx + 1 :]
        if not tail:
            continue
        run_id = tail[0] if len(tail) > 1 else ""
        end = _month_end(int(m.group(1)), int(m.group(2)))
        period = f"{m.group(1)}-{m.group(2)}"
        g = found.setdefault(
            (period, run_id), {"parts": [], "unsupported": [], "end": end, "newest": o.modified}
        )
        g["newest"] = max(g["newest"], o.modified)
        kind = classify(o.key)
        if kind in ("csv", "gz"):
            g["parts"].append(o)
        elif kind.startswith("unsupported:"):
            g["unsupported"].append(kind.split(":", 1)[1])
    return _group("aws", found)


def latest_per_period(runs: list[Run]) -> tuple[list[Run], int]:
    """The newest run of each period, oldest period first, and how many older runs were passed over.
    A later run replaces an earlier one for the same period: exports are cumulative."""
    best: dict[str, Run] = {}
    for r in runs:
        cur = best.get(r.period)
        if cur is None or (r.newest, r.run_id) > (cur.newest, cur.run_id):
            best[r.period] = r
    return sorted(best.values(), key=lambda r: r.period), len(runs) - len(best)
