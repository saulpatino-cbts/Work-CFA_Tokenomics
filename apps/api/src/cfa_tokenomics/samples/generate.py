"""Deterministic synthetic sample exports that all describe the same fictional cast (``cast.py``).

Everything is invented. The layouts follow the vendor documentation recorded in
docs/economics/09-vendor-api-research.md and have NOT been checked against a real export, so these
files test the product's assumptions, not the vendors' behaviour. Every FOCUS row carries
``x_SyntheticSample = true`` so it can never be mistaken for real billing data.

AI cost lines use the FOCUS 1.5 draft's SkuPriceDetails properties. Real AWS and Azure exports do not
carry them today, so those lines are a 1.5-style illustration.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import random
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from . import cast

CENT = Decimal("0.000001")
MILLION = Decimal(1_000_000)
MODELS = {  # placeholder prices per million tokens, not any provider's rates
    "example-model-a": {"in": Decimal("3.00"), "out": Decimal("15.00"), "read": Decimal("0.30")},
    "example-model-b": {"in": Decimal("2.50"), "out": Decimal("10.00"), "read": Decimal("1.25")},
}
CONTRACT_FACTOR = Decimal("0.90")  # a 10% negotiated discount, invented
BASE_INPUT_TOKENS = {
    "claims-assistant": 30_000_000,
    "support-copilot": 18_000_000,
    "dev-assistant": 6_000_000,
}
COLUMNS = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory", "ChargeClass",
    "ChargeDescription", "ChargePeriodStart", "ChargePeriodEnd", "BillingPeriodStart",
    "BillingPeriodEnd", "BillingCurrency", "BillingAccountId", "BillingAccountName", "ServiceName",
    "ServiceCategory", "ServiceProviderName", "HostProviderName", "InvoiceIssuerName",
    "ConsumedQuantity", "ConsumedUnit", "PricingQuantity", "PricingUnit", "SkuId", "SkuPriceId",
    "SkuMeter", "SkuPriceDetails", "Tags", "x_SyntheticSample",
]  # fmt: skip


def _q(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _days(month: str) -> list[date]:
    y, m = (int(x) for x in month.split("-"))
    return [date(y, m, d) for d in range(1, monthrange(y, m)[1] + 1)]


def _stamp(d: date, hour: int = 0) -> str:
    return datetime(d.year, d.month, d.day, hour, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _factor(rng: random.Random, d: date) -> Decimal:
    weekend = Decimal("0.25") if d.weekday() >= 5 else Decimal(1)
    return weekend * (Decimal("0.85") + Decimal(rng.randrange(0, 31)) / Decimal(100))


def _gz(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=6, mtime=0)  # mtime 0: identical bytes every run


def _csv(rows: list[dict], columns: list[str]) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r[c]) for c in columns})
    return out.getvalue().encode()


# ---- cloud cost lines ---------------------------------------------------------------------------


def _line(provider: dict, d: date, month_first: date, month_last: date, **kw) -> dict:
    list_cost = _q(kw.pop("list_cost"))
    contracted = _q(list_cost * kw.pop("factor", CONTRACT_FACTOR))
    row = {
        "BilledCost": str(contracted), "EffectiveCost": str(contracted), "ListCost": str(list_cost),
        "ContractedCost": str(contracted), "ChargeCategory": "Usage", "BillingCurrency": "USD",
        "ChargePeriodStart": _stamp(d), "ChargePeriodEnd": _stamp(d + timedelta(days=1)),
        "BillingPeriodStart": _stamp(month_first), "BillingPeriodEnd": _stamp(month_last + timedelta(days=1)),
        "BillingAccountId": provider["account"], "BillingAccountName": provider["account_name"],
        "ServiceProviderName": provider["name"], "HostProviderName": provider["name"],
        "InvoiceIssuerName": provider["name"], "x_SyntheticSample": "true",
    }  # fmt: skip
    row.update(kw)
    if "Tags" in row and isinstance(row["Tags"], dict):
        row["Tags"] = json.dumps(row["Tags"], sort_keys=True, separators=(",", ":"))
    return row


def _ai_rows(provider, d, first, last, app, model_id, rng, identity) -> list[dict]:
    tokens_in = int(Decimal(BASE_INPUT_TOKENS[app.key]) * _factor(rng, d))
    kinds = (
        ("Input", "Uncached", tokens_in, "in", "input tokens"),
        ("Input", "Read", tokens_in // 2, "read", "cached input tokens"),
        ("Output", None, tokens_in // 4, "out", "output tokens"),
    )
    users = cast.users_of(app.team)
    rows = []
    for k, (direction, action, tokens, price_key, meter) in enumerate(kinds):
        props = {"ModelDeveloper": "Example AI", "ModelFamily": "example-family", "ModelId": model_id,
                 "ModelVersion": "1.0", "TokenDirection": direction}  # fmt: skip
        if action:
            props["TokenCacheAction"] = action
        sku = f"{model_id}-{price_key}"
        row = _line(
            provider, d, first, last,
            list_cost=Decimal(tokens) / MILLION * MODELS[model_id][price_key],
            ChargeDescription=f"{model_id} {meter}", ServiceName=provider["ai_service"],
            ServiceCategory="AI and Machine Learning", ConsumedQuantity=str(tokens), ConsumedUnit="Tokens",
            PricingQuantity=str(Decimal(tokens) / MILLION), PricingUnit="1000000 Tokens", SkuId=sku,
            SkuPriceId=f"{sku}-price", SkuMeter=meter, SkuPriceDetails=json.dumps(props, sort_keys=True, separators=(",", ":")),
            Tags={"app": app.key, "env": "prod"},
        )  # fmt: skip
        if identity:  # FOCUS 1.5 draft identity columns: the importer drops them by default
            u = users[(d.day + k) % len(users)]
            row["PrincipalId"], row["CredentialId"] = (
                f"principal/{u.user_id}",
                f"credential/{u.user_id}",
            )
        rows.append(row)
    return rows


def _infra(
    provider, d, first, last, rng, tagged: dict[str, tuple[str, str, Decimal]], shared: tuple
) -> list[dict]:
    rows = []
    for app_key, (service, category, base) in tagged.items():
        rows.append(_line(
            provider, d, first, last, list_cost=base * _factor(rng, d), ChargeDescription=f"{service} for {app_key}",
            ServiceName=service, ServiceCategory=category, ConsumedQuantity="24", ConsumedUnit="Hours",
            PricingQuantity="24", PricingUnit="Hours", SkuId=f"{service}-sku", SkuPriceId=f"{service}-price",
            SkuMeter="hours", Tags={"app": app_key, "env": "prod"},
        ))  # fmt: skip
    service, category, base = shared  # no app tag: lands in the unallocated bucket
    rows.append(_line(
        provider, d, first, last, list_cost=base, ChargeDescription=f"Shared {service}", ServiceName=service,
        ServiceCategory=category, SkuId=f"{service}-sku", SkuPriceId=f"{service}-price", SkuMeter="shared",
    ))  # fmt: skip
    return rows


def _extras(
    provider, first, last, rows, credit: Decimal, purchase: Decimal | None, correction: tuple
) -> list[dict]:
    out = []
    spend = sum(Decimal(r["BilledCost"]) for r in rows)
    out.append(_line(provider, last, first, last, list_cost=spend * Decimal("0.08"), factor=Decimal(1),
                     ChargeCategory="Tax", ChargeDescription="Sales tax (synthetic 8%)", ServiceName="Tax",
                     ServiceCategory="Other"))  # fmt: skip
    mid = first + timedelta(days=14)
    out.append(_line(provider, mid, first, last, list_cost=-credit, factor=Decimal(1), ChargeCategory="Credit",
                     ChargeDescription="Promotional credit (synthetic)", ServiceName="Credits", ServiceCategory="Other"))  # fmt: skip
    if purchase:
        out.append(_line(provider, first, first, last, list_cost=purchase, factor=Decimal(1), ChargeCategory="Purchase",
                         ChargeDescription="Support plan (synthetic)", ServiceName="Support", ServiceCategory="Other"))  # fmt: skip
    day, amount, model_id = correction
    props = {"ModelDeveloper": "Example AI", "ModelFamily": "example-family", "ModelId": model_id,
             "ModelVersion": "1.0", "TokenDirection": "Output"}  # fmt: skip
    out.append(
        _line(
            provider, day, first, last, list_cost=amount, factor=Decimal(1), ChargeClass="Correction",
            ChargeDescription=f"Correction to {model_id} usage (synthetic)", ServiceName=provider["ai_service"],
            ServiceCategory="AI and Machine Learning", SkuId=f"{model_id}-out", SkuPriceId=f"{model_id}-out-price",
            SkuMeter="output tokens", SkuPriceDetails=json.dumps(props, sort_keys=True, separators=(",", ":")),
        )
    )  # fmt: skip
    return out


AWS = {
    "name": "Amazon Web Services",
    "account": cast.AWS_ACCOUNT,
    "account_name": cast.AWS_ACCOUNT_NAME,
    "ai_service": "Amazon Bedrock",
}
AZURE = {
    "name": "Microsoft",
    "account": cast.AZURE_SUBSCRIPTION,
    "account_name": cast.AZURE_ACCOUNT_NAME,
    "ai_service": "Azure OpenAI",
}


def cost_rows(month: str, seed: int, identity: bool) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    days = _days(month)
    first, last = days[0], days[-1]
    aws, az = [], []
    apps = {a.key: a for a in cast.APPS}
    for d in days:
        for key in ("claims-assistant", "dev-assistant"):
            aws += _ai_rows(AWS, d, first, last, apps[key], "example-model-a", rng, identity)
        az += _ai_rows(
            AZURE, d, first, last, apps["support-copilot"], "example-model-b", rng, False
        )
        aws += _infra(AWS, d, first, last, rng, {
            "claims-assistant": ("Amazon EC2", "Compute", Decimal("18.40")),
            "dev-assistant": ("Amazon EC2", "Compute", Decimal("26.10")),
        }, ("Amazon VPC", "Networking", Decimal("9.75")))  # fmt: skip
        az += _infra(AZURE, d, first, last, rng, {
            "support-copilot": ("Virtual Machines", "Compute", Decimal("22.00")),
        }, ("Azure Support", "Other", Decimal("4.20")))  # fmt: skip
    aws += _extras(
        AWS,
        first,
        last,
        aws,
        Decimal("50.00"),
        Decimal("100.00"),
        (first + timedelta(days=19), Decimal("-1.234567"), "example-model-a"),
    )
    az += _extras(
        AZURE,
        first,
        last,
        az,
        Decimal("25.00"),
        None,
        (first + timedelta(days=19), Decimal("-0.654321"), "example-model-b"),
    )

    def key(r: dict) -> tuple:
        return (r["ChargePeriodStart"], r["ServiceName"], r.get("SkuId") or "", r["ChargeCategory"])

    return sorted(aws, key=key), sorted(az, key=key)


def _split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    mid = len(rows) // 2
    return rows[:mid], rows[mid:]


# ---- OpenAI Daily Usage and Anthropic analytics ------------------------------------------------------


def _openai(month: str, seed: int) -> tuple[dict, dict]:
    rng = random.Random(seed + 1)
    credit_usd = Decimal(cast.CREDIT_USD)
    per_user: list[dict] = []
    for d in _days(month):
        start = int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())
        for u in cast.USERS:
            heavy = u.team == "platform-eng"
            if d.weekday() >= 5 and rng.random() < 0.8:
                continue  # most people do not work weekends
            clients = []
            for cid in ("CODEX_CLI", "CODEX_WEB"):
                turns = rng.randrange(0, 40 if heavy else 8)
                if not turns:
                    continue
                credits = round(turns * rng.uniform(1.5, 3.5), 4)
                clients.append({"client_id": cid, "chats": max(1, turns // 6), "messages": turns, "credits": credits,
                                "estimated_cost_usd": float((Decimal(str(credits)) * credit_usd).quantize(Decimal("0.01")))})  # fmt: skip
            if not clients:
                continue
            credits = round(
                sum(c["credits"] for c in clients) + (0.5 if rng.random() < 0.1 else 0.0), 4
            )
            totals = {"chats": sum(c["chats"] for c in clients), "messages": sum(c["messages"] for c in clients),
                      "credits": credits, "estimated_cost_usd": float((Decimal(str(credits)) * credit_usd).quantize(Decimal("0.01")))}  # fmt: skip
            row = {"object": "workspace.usage.result", "start_time": start, "end_time": start + 86400, "user_id": u.user_id,
                   "actor": {"type": "ACCOUNT_USER", "user_id": u.user_id, "email": u.email}, "totals": totals,
                   "clients": clients, "models": [{"model": "example-model-a", "speed": "standard", "credits": credits,
                                                   "estimated_cost_usd": totals["estimated_cost_usd"]}]}  # fmt: skip
            if (
                heavy and u.user_id in ("user-0009", "user-0010") and d.day % 3 == 0
            ):  # an API-priced day: USD, tokens, no credits
                usd = round(rng.uniform(1.0, 6.0), 4)
                tin = rng.randrange(200_000, 900_000)
                totals.update(credits=None, cost_usd=usd, uncached_text_input_tokens=tin, cached_text_input_tokens=tin // 2,
                              text_output_tokens=tin // 5, text_total_tokens=tin + tin // 2 + tin // 5)  # fmt: skip
                totals.pop("estimated_cost_usd")
                row["models"] = [
                    {
                        "model": "example-model-a",
                        "speed": "standard",
                        "credits": None,
                        "cost_usd": usd,
                    }
                ]
                for c in clients:
                    c["credits"] = None
                    c.pop("estimated_cost_usd")
            if heavy:
                row["code_attribution"] = {"lines_of_code": {"added": rng.randrange(50, 900)},
                                           "commits": {"with_codex_contribution": rng.randrange(1, 9),
                                                       "with_codex_contribution_percentage": 40.0, "total_commits": 12}}  # fmt: skip
            per_user.append(row)
    ws: dict[int, dict] = {}
    for r in per_user:
        w = ws.setdefault(r["start_time"], {"object": "workspace.usage.result", "start_time": r["start_time"], "end_time": r["end_time"],
                                            "user_id": None, "actor": None, "chats": 0, "messages": 0, "credits": Decimal(0), "usd": Decimal(0)})  # fmt: skip
        w["chats"] += r["totals"]["chats"]
        w["messages"] += r["totals"]["messages"]
        w["credits"] += Decimal(str(r["totals"]["credits"] or 0))
        w["usd"] += Decimal(str(r["totals"].get("cost_usd") or 0))
    workspace = []
    for start in sorted(ws):
        w = ws[start]
        totals = {"chats": w["chats"], "messages": w["messages"], "credits": float(w["credits"]) if w["credits"] else None,
                  "cost_usd": float(w["usd"]) if w["usd"] else None}  # fmt: skip
        if w["credits"]:
            totals["estimated_cost_usd"] = float(
                (w["credits"] * credit_usd).quantize(Decimal("0.01"))
            )
        workspace.append({"object": w["object"], "start_time": start, "end_time": w["end_time"], "user_id": None, "actor": None,
                          "totals": totals, "clients": []})  # fmt: skip

    def page(rows: list[dict]) -> dict:
        return {"object": "page", "data": rows, "has_more": False, "next_page": None}

    return page(per_user), page(workspace)


_GROUP_KEYS = ("product", "model", "context_window", "inference_geo", "speed", "slack_channel_id", "claude_tag_category",
               "claude_tag_user_id", "rbac_group_id", "workspace_id", "service_tier", "user_profile_id", "agent_id",
               "environment_id", "deployment_id", "session_id", "actor", "actor_type", "api_key_id")  # fmt: skip
_TOKEN_TYPES = ("uncached_input_tokens", "cache_creation.ephemeral_5m_input_tokens", "cache_creation.ephemeral_1h_input_tokens",
                "cache_read_input_tokens", "output_tokens")  # fmt: skip


def _anthropic(month: str, seed: int) -> dict[str, dict]:
    rng = random.Random(seed + 2)
    dev = cast.users_of("platform-eng")
    price = MODELS["example-model-a"]
    refreshed = _stamp(_days(month)[-1] + timedelta(days=2), 4)
    use_model, cost_model, use_actor = [], [], []
    for d in _days(month):
        s, e = _stamp(d), _stamp(d + timedelta(days=1))
        per_user = {}
        for u in dev:
            if d.weekday() >= 5:
                continue
            base = rng.randrange(300_000, 1_500_000)
            per_user[u] = {"uncached_input_tokens": base, "cache_read_input_tokens": base * 2,
                           "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": base // 10},
                           "output_tokens": base // 3}  # fmt: skip
        if not per_user:
            continue
        for u, usage in per_user.items():
            usage["total_tokens"] = (usage["uncached_input_tokens"] + usage["cache_read_input_tokens"] + usage["output_tokens"]
                                     + sum(usage["cache_creation"].values()))  # fmt: skip
            usage["server_tool_use"] = {"web_search_requests": 0}
            usage["requests"] = usage["output_tokens"] // 800
            g = dict.fromkeys(_GROUP_KEYS)
            g.update(actor={"type": "user_actor", "user_id": u.user_id, "email_address": u.email, "name": None, "deleted": False},
                     actor_type="user_actor", model="example-model-a")  # fmt: skip
            use_actor.append({"starting_at": s, "ending_at": e, "group": g, "usage": usage})
        agg = {
            k: sum(p[k] for p in per_user.values())
            for k in (
                "uncached_input_tokens",
                "cache_read_input_tokens",
                "output_tokens",
                "total_tokens",
                "requests",
            )
        }
        agg["cache_creation"] = {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": sum(p["cache_creation"]["ephemeral_5m_input_tokens"] for p in per_user.values())}  # fmt: skip
        agg["server_tool_use"] = {"web_search_requests": 0}
        g = dict.fromkeys(_GROUP_KEYS)
        g.update(
            model="example-model-a", workspace_id="wrkspc_example0001", service_tier="standard"
        )
        use_model.append({"starting_at": s, "ending_at": e, "group": g, "usage": agg})
        per_type = {"uncached_input_tokens": (agg["uncached_input_tokens"], price["in"]), "cache_read_input_tokens": (agg["cache_read_input_tokens"], price["read"]),
                    "output_tokens": (agg["output_tokens"], price["out"]),
                    "cache_creation.ephemeral_5m_input_tokens": (agg["cache_creation"]["ephemeral_5m_input_tokens"], price["in"] * Decimal("1.25")),
                    "cache_creation.ephemeral_1h_input_tokens": (0, price["in"] * 2)}  # fmt: skip
        for ttype in _TOKEN_TYPES:
            tokens, per_m = per_type[ttype]
            list_cents = _q(Decimal(tokens) / MILLION * per_m * 100)
            gg = dict.fromkeys(_GROUP_KEYS)
            gg.update(
                model="example-model-a",
                workspace_id="wrkspc_example0001",
                service_tier="standard",
                cost_type="tokens",
                token_type=ttype,
            )
            cost_model.append({"starting_at": s, "ending_at": e, "group": gg,
                               "cost": {"amount": f"{_q(list_cents * CONTRACT_FACTOR):f}", "list_amount": f"{list_cents:f}", "currency": "USD", "requests": None}})  # fmt: skip

    def env(rows: list[dict]) -> dict:
        return {
            "data": rows,
            "has_more": False,
            "next_page": None,
            "data_refreshed_at": refreshed,
        }

    return {"analytics_usage_by_model.json": env(use_model), "analytics_cost_by_model.json": env(cost_model),
            "analytics_usage_by_actor.json": env(use_actor)}  # fmt: skip


# ---- assembling the files ---------------------------------------------------------------------------


def build_all(month: str = "2026-10", seed: int = 7, identity: bool = False) -> dict[str, bytes]:
    """Relative path to file content, identical for the same arguments."""
    aws, az = cost_rows(month, seed, identity)
    cols = COLUMNS + (["PrincipalId", "CredentialId"] if identity else [])
    y, m = month.split("-")
    files: dict[str, bytes] = {}
    for i, part in enumerate(_split(aws), 1):
        files[f"aws/cur/focus/data/BILLING_PERIOD={month}/export-{i:05d}.csv.gz"] = _gz(
            _csv(part, cols)
        )
    files[f"aws/cur/focus/metadata/BILLING_PERIOD={month}/export-Manifest.json"] = _json(
        {"synthetic": True, "billing_period": month}
    )
    last = _days(month)[-1]
    period = f"{y}{m}01-{y}{m}{last.day:02d}"
    for i, part in enumerate(_split(az), 1):
        files[f"azure/ea/focus/{period}/run-0001/part_{i:04d}.csv.gz"] = _gz(_csv(part, COLUMNS))
    files[f"azure/ea/focus/{period}/run-0001/manifest.json"] = _json(
        {"synthetic": True, "manifestVersion": "synthetic"}
    )
    per_user, workspace = _openai(month, seed)
    files["openai/daily_usage_per_user.json"] = _json(per_user)
    files["openai/daily_usage_workspace.json"] = _json(workspace)
    for name, doc in _anthropic(month, seed).items():
        files[f"anthropic/{name}"] = _json(doc)
    files["README.txt"] = README.encode()
    return files


def _json(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1) + "\n").encode()


README = """SYNTHETIC SAMPLE DATA - not real billing, usage or people.

Everything here is invented: the organisation (Example Co), the twelve users (user-0001 to
user-0012 at example.test), the accounts, the models (example-model-a and -b) and every price.
Each FOCUS cost row has x_SyntheticSample = true.

aws/        a FOCUS-style export tree, as AWS Data Exports lays it out (CSV gzip, two parts)
azure/      a FOCUS-style export tree, as an Azure Cost Management export lays it out (CSV gzip, two parts)
openai/     the unified Daily Usage API, per user and workspace-wide (credits, USD, text tokens kept separate)
anthropic/  the usage and cost analytics API, by model, and usage by actor (cost amounts are cents as strings)

The layouts and shapes follow vendor documentation and are NOT verified against a real export or a
live API. See docs/economics/09-vendor-api-research.md.
"""


def write(out_dir: str, month: str = "2026-10", seed: int = 7, identity: bool = False) -> list[str]:
    import os

    paths = []
    for rel, data in build_all(month, seed, identity).items():
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        paths.append(rel)
    return sorted(paths)
