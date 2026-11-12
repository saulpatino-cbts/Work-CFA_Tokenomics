"""Sanitize FOCUS CSV exports (plain or gzip) so a real export can be shared for testing.

How it stays safe:
- **An allow-list, not a block-list.** Only columns known to hold non-identifying values pass through. Every
  other column is dropped, including any extension column (``x_...``), free-text descriptions and the FOCUS 1.5
  identity columns. ``--allow-columns`` lets the owner keep more, on their own judgement.
- **Identifiers become pseudonyms.** Account, resource and invoice identifiers are replaced by a keyed hash,
  consistently within a run (and across runs only if the owner keeps a salt file), so grouping, joins and
  allocation still work. The salt is random, never printed and never written to the report.
- **Text is scrubbed.** Emails, ARNs, GUIDs, 12-digit account numbers and IPv4 addresses inside kept text,
  tag keys and tag values and ``SkuPriceDetails`` are replaced.
- **A leak check runs last.** If an email or an ARN is still anywhere in the output, the output is deleted and
  the run fails.
- **Amounts stay real unless scaled.** Costs and quantities are the customer's actual figures. ``--scale``
  multiplies cost and quantity columns by an exact decimal (unit prices are left alone, so cost still equals
  quantity times price within rounding at 18 decimal places), which keeps ratios and hides absolute spend.
  The factor is never printed or recorded.

This reduces what a file reveals; it does not prove anonymity. Dates, services, regions, SKUs and the shape of
spend remain, and a determined reader who knows the customer could still recognise them. The owner reviews the
output before sharing it.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

KEEP = frozenset({
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ListUnitPrice", "ContractedUnitPrice",
    "ConsumedQuantity", "PricingQuantity", "ChargeCategory", "ChargeClass", "ChargeFrequency",
    "ChargePeriodStart", "ChargePeriodEnd", "BillingPeriodStart", "BillingPeriodEnd", "BillingCurrency",
    "PricingCurrency", "ConsumedUnit", "PricingUnit", "ServiceCategory", "ServiceSubcategory", "ServiceName",
    "ServiceProviderName", "HostProviderName", "InvoiceIssuerName", "ProviderName", "PricingCategory",
    "SkuId", "SkuPriceId", "SkuMeter", "SkuPriceDetails", "RegionId", "RegionName", "AvailabilityZone",
    "ResourceType", "CommitmentDiscountCategory", "CommitmentDiscountType", "CommitmentDiscountStatus",
    "CommitmentDiscountUnit", "CommitmentDiscountQuantity", "AllocatedMethodId", "AllocatedServiceName",
})  # fmt: skip
PSEUDONYMIZE = {
    "BillingAccountId": "acct", "BillingAccountName": "acctname", "SubAccountId": "sub", "SubAccountName": "subname",
    "ResourceId": "res", "ResourceName": "resname", "InvoiceId": "inv", "InvoiceDetailId": "invd",
    "CommitmentDiscountId": "cd", "CommitmentDiscountName": "cdname", "AllocatedResourceId": "ares",
    "AllocatedResourceName": "aresname",
}  # fmt: skip
TAG_COLUMNS = ("Tags", "AllocatedTags")
SCALED = frozenset(
    {
        "BilledCost",
        "EffectiveCost",
        "ListCost",
        "ContractedCost",
        "ConsumedQuantity",
        "PricingQuantity",
        "CommitmentDiscountQuantity",
    }
)
NOT_SCRUBBED = frozenset(
    {"SkuId", "SkuPriceId", "SkuMeter"}
)  # public catalog identifiers, often GUID-shaped
_TAG_KEY = re.compile(r"^[a-z][a-z0-9_:.-]{0,40}$")
PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "arn": re.compile(r"arn:[\w-]+:[^\s\"',;]*"),
    "guid": re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"),
    "account12": re.compile(r"\b\d{12}\b"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}
LEAK = ("email", "arn")  # strong signals: if either survives, the output is deleted
QUANT = Decimal(1).scaleb(-18)


class SanitizeError(Exception):
    pass


@dataclass
class Options:
    salt: bytes
    scale: Decimal | None = None
    keep_tag_values_for: frozenset[str] = frozenset()
    allow_columns: frozenset[str] = frozenset()


@dataclass
class FileReport:
    path: str
    rows: int = 0
    kept: list[str] = field(default_factory=list)
    pseudonymized: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    scrubbed: dict[str, int] = field(default_factory=dict)
    scaled: bool = False


class Sanitizer:
    def __init__(self, opts: Options):
        if len(opts.salt) < 16:
            raise SanitizeError("the salt must be at least 16 bytes")
        self.o = opts
        self.unique: dict[str, set[str]] = {}

    def pseudonym(self, kind: str, value: str) -> str:
        mac = hmac.new(self.o.salt, f"{kind}\x00{value}".encode(), hashlib.sha256).hexdigest()[:12]
        self.unique.setdefault(kind, set()).add(mac)
        return f"{kind}-{mac}"

    def scrub(self, text: str, counts: dict[str, int]) -> str:
        for name, pat in PATTERNS.items():

            def sub(m: re.Match, name=name) -> str:
                counts[name] = counts.get(name, 0) + 1
                return self.pseudonym(f"x{name}", m.group(0))

            text = pat.sub(sub, text)
        return text

    def tags(self, raw: str, counts: dict[str, int]) -> str:
        if not raw.strip():
            return ""
        try:
            obj = json.loads(raw)
        except ValueError:
            return ""  # unparseable tags are dropped, not guessed at
        if not isinstance(obj, dict):
            return ""
        out = {}
        for k, v in obj.items():
            key = (
                k
                if isinstance(k, str) and _TAG_KEY.match(k) and not PATTERNS["email"].search(k)
                else self.pseudonym("tagkey", str(k))
            )
            val = "" if v is None else str(v)
            out[key] = (
                self.scrub(val, counts)
                if k in self.o.keep_tag_values_for
                else self.pseudonym("tagval", val)
            )
        return json.dumps(out, sort_keys=True, separators=(",", ":"))

    def scale(self, value: str) -> str:
        if not value.strip() or self.o.scale is None:
            return value
        try:
            d = Decimal(value) * self.o.scale
        except InvalidOperation:
            return value  # a non-numeric cell is left for the importer to reject, as it would have been
        return f"{d.quantize(QUANT, rounding=ROUND_HALF_EVEN).normalize():f}"  # exact, with padding zeros trimmed

    def row(
        self, row: dict[str, str], keep: list[str], pseudo: list[str], counts: dict[str, int]
    ) -> dict[str, str]:
        out = {}
        for c in keep:
            v = row.get(c) or ""
            if c in TAG_COLUMNS:
                out[c] = self.tags(v, counts)
            elif c in SCALED:
                out[c] = self.scale(v)
            elif c in NOT_SCRUBBED or not v:
                out[c] = v
            else:
                out[c] = self.scrub(v, counts)
        for c in pseudo:
            v = row.get(c) or ""
            out[c] = self.pseudonym(PSEUDONYMIZE[c], v) if v else ""
        return out


def _open(path: str):
    raw = open(path, "rb")
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8-sig", newline="")
    return io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")


def sanitize_file(src: str, dst: str, sanitizer: Sanitizer, rel: str = "") -> FileReport:
    """Sanitize one CSV. On any failure, including the leak check, the output file is removed."""
    rep = FileReport(rel or os.path.basename(src))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    allow = sanitizer.o.allow_columns
    try:
        with _open(src) as fh:
            reader = csv.DictReader(fh)
            header = [h.strip() for h in (reader.fieldnames or [])]
            if not header:
                raise SanitizeError("the file has no header row")
            reader.fieldnames = header
            keep = [c for c in header if c in KEEP or c in TAG_COLUMNS or c in allow]
            pseudo = [c for c in header if c in PSEUDONYMIZE]
            rep.kept, rep.pseudonymized = keep, pseudo
            rep.dropped = [c for c in header if c not in keep and c not in pseudo]
            cols = [c for c in header if c in keep or c in pseudo]
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            for r in reader:
                if None in r:
                    raise SanitizeError("a row had more cells than the header")
                w.writerow(sanitizer.row(r, keep, pseudo, rep.scrubbed))
                rep.rows += 1
        text = buf.getvalue()
        for name in LEAK:  # the last line of defence
            if PATTERNS[name].search(text):
                raise SanitizeError(
                    f"a {name}-shaped value survived sanitizing in {rel or src}; nothing was written"
                )
        data = text.encode()
        with open(dst, "wb") as out:
            out.write(gzip.compress(data, mtime=0) if dst.endswith(".gz") else data)
        rep.scaled = sanitizer.o.scale is not None
        return rep
    except BaseException:
        if os.path.exists(dst):
            os.remove(dst)
        raise


def sanitize_tree(src: str, dst: str, opts: Options) -> dict:
    """A file or a whole export tree. Folder layout is kept (so connector layouts still match); only CSV files
    are written, everything else is skipped and listed."""
    if os.path.exists(dst) and (os.path.isfile(dst) or os.listdir(dst)):
        raise SanitizeError("the output already exists and is not empty; choose a new path")
    s = Sanitizer(opts)
    reports, skipped = [], []
    if os.path.isfile(src):
        pairs = [(src, dst, os.path.basename(src))]
        report_path = dst + ".report.json"
    else:
        pairs = []
        for root, _dirs, names in os.walk(src):
            for n in sorted(names):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, src)
                if n.lower().endswith((".csv", ".csv.gz")):
                    pairs.append((p, os.path.join(dst, rel), rel))
                else:
                    skipped.append(rel)
        report_path = os.path.join(dst, "sanitize-report.json")
    if not pairs:
        raise SanitizeError("no CSV files were found")
    written = []
    try:
        for p, d, rel in sorted(pairs):
            reports.append(sanitize_file(p, d, s, rel))
            written.append(d)
    except BaseException:
        for d in written:  # all or nothing: a failure leaves no partial output behind
            if os.path.exists(d):
                os.remove(d)
        raise
    report = {
        "files": [r.__dict__ for r in reports], "skipped_not_csv": sorted(skipped),
        "pseudonyms_by_kind": {k: len(v) for k, v in sorted(s.unique.items())},
        "note": "Amounts are real unless --scale was used. Review the output before sharing it.",
    }  # fmt: skip
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    return report


def load_salt(path: str | None) -> tuple[bytes, bool]:
    """A salt file keeps pseudonyms consistent between runs. Without one the salt lives only in memory."""
    if not path:
        return secrets.token_bytes(32), False
    if os.path.exists(path):
        with open(path, "rb") as fh:
            salt = fh.read()
        if len(salt) < 16:
            raise SanitizeError("the salt file is too short to be a salt")
        return salt, False
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        salt = secrets.token_bytes(32)
        fh.write(salt)
    return salt, True


def main(argv: list[str]) -> int:
    usage = (
        "python -m cfa_tokenomics.sanitize INPUT OUTPUT [--salt-file FILE] [--scale DECIMAL]\n"
        "    [--keep-tag-values-for KEY,KEY] [--allow-columns COL,COL]\n"
        "INPUT is a FOCUS CSV (plain or .gz) or a folder of them; OUTPUT must not exist yet."
    )
    if len(argv) < 2 or argv[0].startswith("-") or argv[1].startswith("-"):
        print(usage, file=sys.stderr)
        return 2

    def opt(name: str) -> str | None:
        return (
            argv[argv.index(name) + 1]
            if name in argv and argv.index(name) + 1 < len(argv)
            else None
        )

    try:
        scale = None
        if opt("--scale") is not None:
            scale = Decimal(opt("--scale") or "")
            if not scale.is_finite() or scale <= 0:
                raise SanitizeError("--scale must be a positive decimal")
        salt, created = load_salt(opt("--salt-file"))
        opts = Options(
            salt, scale, frozenset(filter(None, (opt("--keep-tag-values-for") or "").split(","))),
            frozenset(filter(None, (opt("--allow-columns") or "").split(","))),
        )  # fmt: skip
        rep = sanitize_tree(argv[0], argv[1], opts)
    except (SanitizeError, InvalidOperation, OSError, UnicodeError, csv.Error) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    for f in rep["files"]:
        print(
            f"{f['path']}: {f['rows']} rows; kept {len(f['kept'])}, pseudonymized {len(f['pseudonymized'])}, dropped {len(f['dropped'])} column(s)"
        )
    if rep["skipped_not_csv"]:
        print(f"skipped (not CSV): {', '.join(rep['skipped_not_csv'])}")
    if created:
        print(
            "created a salt file; keep it private. It is what makes pseudonyms repeat across runs."
        )
    print("done. Amounts are real unless --scale was used. Review the output before you share it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
