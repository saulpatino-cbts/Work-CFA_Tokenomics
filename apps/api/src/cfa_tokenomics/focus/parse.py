"""Pure FOCUS CSV parser. No database, clock or network: the same bytes always give the same result.

Rules: nothing is silently coerced or rounded. A row that cannot be represented exactly is
rejected with a reason code and the rest of the file is still imported. Unrecognized columns are
preserved as extensions, never dropped.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import columns as C

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_OFFSET = re.compile(r"^([+-])(\d{2}):(\d{2})$")


class FileError(Exception):
    """The whole file cannot be imported (too large, undecodable, missing required columns)."""


@dataclass(frozen=True)
class Reject:
    row_number: int  # 1 is the header, so the first data row is 2
    reason: str
    column: str | None = None


@dataclass
class ParsedRow:
    row_number: int
    values: dict[str, Any]
    extensions: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    rejects: list[Reject]
    columns: list[str]
    unknown_columns: list[str]
    aliases_used: dict[str, str]
    declared_version: str
    dropped_identity_columns: list[str] = field(default_factory=list)
    # Provenance for timestamps that carried no timezone: the zone that was assumed and how many
    # timestamp values it was applied to. Zero when every timestamp stated its own offset.
    assumed_timezone: str | None = None
    naive_timestamps_assumed: int = 0


def decompress(raw: bytes, max_bytes: int) -> bytes:
    """Return the CSV bytes, expanding gzip if present. Both sizes are capped."""
    if len(raw) > max_bytes:
        raise FileError(f"file is larger than the {max_bytes} byte limit")
    if raw[:2] != b"\x1f\x8b":
        return raw
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
            out = fh.read(max_bytes + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise FileError(f"corrupt gzip data: {exc}") from None
    if len(out) > max_bytes:
        raise FileError(f"decompressed data is larger than the {max_bytes} byte limit")
    return out


def _decimal(text: str) -> Decimal:
    try:
        d = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("not_a_number") from None
    if not d.is_finite():
        raise ValueError("not_finite")
    exp = d.as_tuple().exponent
    if isinstance(exp, int) and -exp > C.MAX_DECIMAL_PLACES:
        # Trailing zeros beyond the limit are harmless; anything real would be rounded, so refuse.
        if d != d.quantize(Decimal(1).scaleb(-C.MAX_DECIMAL_PLACES)):
            raise ValueError("too_many_decimals")
    return d


def _typed_optional(cells: dict[str, str], col: str) -> str:
    """The text of an optional typed cell, with the literal ``NULL`` read as empty (unknown).

    Some published FOCUS samples write ``NULL`` for a missing value. In a number, timestamp or JSON
    column that can only mean null, so it is read as not reported, never as zero. Required columns
    are not affected: a missing required value is still rejected.
    """
    v = cells.get(col, "").strip()
    return "" if v == "NULL" else v


def resolve_timezone(name: str) -> tzinfo:
    """``UTC``, a fixed offset such as ``+05:30``, or an IANA name such as ``America/Chicago``.

    Named zones need the system zone database or the ``tzdata`` package; an unknown name is an
    error, never a silent fallback to UTC.
    """
    name = name.strip()
    if name.upper() in ("UTC", "Z"):
        return UTC
    m = _OFFSET.match(name)
    if m:
        hours, minutes = int(m.group(2)), int(m.group(3))
        if hours > 23 or minutes > 59:
            raise FileError(f"timezone offset out of range: {name}")
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(-delta if m.group(1) == "-" else delta)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise FileError(f"unknown timezone: {name!r}") from None


def _timestamp(text: str, assume: tzinfo | None = None) -> tuple[datetime, bool]:
    """Return the instant in UTC and whether ``assume`` had to be applied (no zone in the text)."""
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError:
        raise ValueError("bad_timestamp") from None
    if dt.tzinfo is None:
        if assume is None:
            raise ValueError("timestamp_without_timezone")
        return dt.replace(tzinfo=assume).astimezone(UTC), True
    return dt.astimezone(UTC), False


def _json_object(text: str) -> dict[str, Any]:
    try:
        v = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("bad_json") from None
    if not isinstance(v, dict):
        raise ValueError("json_not_an_object")
    return v


def parse_focus_csv(
    raw: bytes,
    declared_version: str = "unknown",
    max_bytes: int = 100_000_000,
    keep_identity_columns: bool = False,
    assume_timezone: str | None = "UTC",
) -> ParseResult:
    if declared_version not in C.DECLARED_VERSIONS:
        raise FileError(f"declared FOCUS version must be one of {', '.join(C.DECLARED_VERSIONS)}")
    data = decompress(raw, max_bytes)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileError("file is not valid UTF-8") from None
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise FileError("file is empty") from None
    if len(set(header)) != len(header):
        raise FileError("duplicate column names in the header")

    aliases: dict[str, str] = {}
    present = set(header)
    for legacy, current in C.LEGACY_ALIASES.items():
        if legacy in present and current not in present:
            aliases[legacy] = current
    effective = {aliases.get(h, h) for h in header}
    required = C.REQUIRED + C.VERSION_MANDATORY.get(declared_version, ())
    missing = [c for c in required if c not in effective]
    if missing:
        raise FileError(f"missing required columns: {', '.join(missing)}")
    identity = [h for h in header if h in C.IDENTITY_COLUMNS]
    unknown = [
        h for h in header if h not in C.KNOWN and (keep_identity_columns or h not in identity)
    ]

    assume = resolve_timezone(assume_timezone) if assume_timezone is not None else None
    naive_total = 0

    rows: list[ParsedRow] = []
    rejects: list[Reject] = []
    for n, record in enumerate(reader, start=2):
        if not record or all(c.strip() == "" for c in record):
            continue
        if len(record) != len(header):
            rejects.append(Reject(n, "column_count"))
            continue
        cells = {aliases.get(h, h): v for h, v in zip(header, record, strict=True)}
        values: dict[str, Any] = {}
        reject: Reject | None = None
        naive_in_row = 0

        def ts(text: str) -> datetime:
            nonlocal naive_in_row
            dt, was_naive = _timestamp(text, assume)
            naive_in_row += was_naive
            return dt

        def fail(reason: str, col: str, _n: int = n) -> Reject:
            return Reject(_n, reason, col)

        for col, attr in C.DECIMAL_REQUIRED.items():
            try:
                if cells[col].strip() == "":
                    raise ValueError("missing_required_value")
                values[attr] = _decimal(cells[col])
            except ValueError as exc:
                reject = fail(str(exc), col)
                break
        if reject is None:
            for col, attr in C.TIMESTAMP_REQUIRED.items():
                try:
                    if cells[col].strip() == "":
                        raise ValueError("missing_required_value")
                    values[attr] = ts(cells[col])
                except ValueError as exc:
                    reject = fail(str(exc), col)
                    break
        if reject is None and values["charge_period_end"] <= values["charge_period_start"]:
            reject = fail("charge_period_not_positive", "ChargePeriodEnd")
        if reject is None:
            for col, attr in {**C.DECIMAL_OPTIONAL}.items():
                if _typed_optional(cells, col) != "":
                    try:
                        values[attr] = _decimal(cells[col])
                    except ValueError as exc:
                        reject = fail(str(exc), col)
                        break
        if reject is None:
            for col, attr in C.TIMESTAMP_OPTIONAL.items():
                if _typed_optional(cells, col) != "":
                    try:
                        values[attr] = ts(cells[col])
                    except ValueError as exc:
                        reject = fail(str(exc), col)
                        break
        if reject is None:
            for col, attr in C.CURRENCY.items():
                v = cells.get(col, "").strip()
                if col == "BillingCurrency" and not v:
                    reject = fail("missing_required_value", col)
                    break
                if v:
                    if col == "PricingCurrency":
                        ok = len(v) <= C.PRICING_CURRENCY_MAX_LENGTH and not any(
                            ch.isspace() for ch in v
                        )
                    else:
                        ok = bool(_CURRENCY.match(v))
                    if not ok:
                        reject = fail("bad_currency", col)
                        break
                    values[attr] = v
        if reject is None:
            for col, attr in C.JSON_OBJECT.items():
                if _typed_optional(cells, col) != "":
                    try:
                        values[attr] = _json_object(cells[col])
                    except ValueError as exc:
                        reject = fail(str(exc), col)
                        break
        if reject is None:
            cat = cells["ChargeCategory"].strip()
            if cat not in C.CHARGE_CATEGORIES:
                reject = fail("unknown_charge_category", "ChargeCategory")
            else:
                values["charge_category"] = cat
        if reject is not None:
            rejects.append(reject)
            continue
        for col, attr in C.STRING.items():
            if col == "ChargeCategory":
                continue
            v = cells.get(col, "")
            if v.strip() != "":
                values[attr] = v
        ext = {h: v for h, v in zip(header, record, strict=True) if h in unknown and v != ""}
        if naive_in_row:
            naive_total += naive_in_row
            ext["_assumed_timezone"] = assume_timezone or ""
        for legacy in aliases:
            ext[f"_alias:{legacy}"] = aliases[legacy]
        rows.append(ParsedRow(n, values, ext))
    return ParseResult(
        rows,
        rejects,
        header,
        unknown,
        aliases,
        declared_version,
        [] if keep_identity_columns else identity,
        assumed_timezone=assume_timezone if naive_total else None,
        naive_timestamps_assumed=naive_total,
    )
