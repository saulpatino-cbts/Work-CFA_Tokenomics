# 4. Connector framework

**Status:** proposed. Part of the [AI economics redesign](README.md). The capability matrix is drawn from vendor documentation read on 2026-11-07. Items the pages did not state are marked **not found**; items from truncated pages are marked **(summary)**. Re-verify each source before building its connector, because these APIs change (several are in beta).

## Principles

1. **Land raw first.** A connector returns unmodified payloads plus metadata. A separate, versioned, pure **mapper** turns raw into normalized facts, so history can be re-mapped without re-pulling.
2. **Declare what you can measure.** A connector publishes a manifest of measures, grains, delays and permissions. The product never assumes token telemetry exists.
3. **All provider logic lives here.** No business logic branches on a vendor.
4. **Server-side only, least privilege, read-only.** Credentials are secret-store references resolved by workers. No credential reaches the browser, a log or a raw payload.
5. **Minimize on ingest.** Drop what the product does not need (prompt and response bodies, user names) before landing, or pseudonymize it.
6. **Be honest about time.** Record each source's delay and revision window; mark facts `provisional` until it closes.

## Contract

```text
Connector
  manifest()                          -> Manifest      measures, grains, delay, revision window, auth kind,
                                                       required permissions, rate-limit notes, FOCUS version emitted
  validate_credentials(ref)           -> CredentialStatus
  discover(ref)                       -> Scope[]       accounts, subscriptions, projects, workspaces, resources
  pull(scope, window, cursor)         -> RawBatch      payload refs + content hash + next cursor + completeness
Mapper (versioned, pure, no I/O)
  map(raw, scope, mapper_version)     -> Usage[], Cost[], Resource[], with basis and finality set
```

Rules: `pull` is idempotent for a window; the cursor advances only after the raw batch is durably stored; partial data is flagged and does not advance the cursor; every request uses bounded retries with backoff and honors the source's rate limits (several limits are **not found** in the documentation, so none is assumed); mappers never call out, so replay is deterministic.

**Registry and onboarding.** A connector registers its manifest. The UI shows the permission checklist, runs `validate_credentials`, then `discover`, then a dry-run `pull`, and reports each step separately (identity, network, access, data), as the earlier setup design intended.

**Health.** Per connector: credential status, last success, lag versus the manifest's expected delay, last error class, rows ingested, schema drift (unexpected fields), and permission over-grant where inspectable. Surfaced on a health screen and alertable.

**Manual import is a first-class connector.** It accepts FOCUS files (CSV or Parquet, any version from 1.0), a generic CSV with a saved column mapping, and a usage template. It is the fastest route to real data, the fallback for sources with no API, and the way customers supply price sheets and invoices.

## Sharing a real export safely: the sanitizer

`python -m cfa_tokenomics.sanitize INPUT OUTPUT [--salt-file FILE] [--scale DECIMAL] [--keep-tag-values-for KEY,KEY] [--allow-columns COL,COL]` takes a real FOCUS CSV (plain or gzip) or a whole export folder and writes a copy that is safer to share for testing. It runs locally, calls nothing and writes only to a new path. **Tested on invented stand-ins for sensitive values, never on a real export.**

- **Allow-list.** Only columns known to hold non-identifying values pass through (costs, quantities, dates, currency, categories, units, service and SKU names, regions, commitment categories). **Every other column is dropped**, including extension columns (`x_...`), free-text descriptions, `ChargeDescription`, and the FOCUS 1.5 identity columns. The report names the dropped columns, never their values.
- **Pseudonyms.** Account, resource, invoice and commitment identifiers and names become consistent keyed pseudonyms (`acct-…`, `res-…`), so grouping, joins and allocation still work. The salt is random, never printed and never written to the report. With `--salt-file` the same salt (created `0600` if absent) is reused so pseudonyms match across runs; without it they are unlinkable between runs. **Run the whole folder in one invocation**, since parts of one export must share a salt.
- **Scrubbing.** Emails, ARNs, GUIDs, 12-digit account numbers and IPv4 addresses inside kept text, tag keys and values and `SkuPriceDetails` are replaced. SKU identifiers (`SkuId`, `SkuPriceId`, `SkuMeter`) are public catalog ids and are left alone so they stay joinable to price lists.
- **Tags.** Simple lower-case keys are kept; other keys and all values become pseudonyms, except values for keys named in `--keep-tag-values-for` (for example `app,env`, so tag allocation still reads naturally). Unreadable tags are dropped.
- **Amounts are real unless scaled.** `--scale 0.37` multiplies cost and quantity columns by an exact decimal (unit prices are untouched, so cost still equals quantity times price within rounding at 18 decimal places), which keeps ratios and hides absolute spend. The factor is never printed or recorded.
- **Leak check.** After writing, any email or ARN still anywhere in the output deletes it and fails the run. A failure on any file removes every file already written.
- **Layout is preserved** (so the connector layouts still match); non-CSV files are skipped and listed.

**Limits.** It reduces what a file reveals; it does not prove anonymity. Dates, services, regions, SKUs, tag keys and the shape of spend remain, and someone who knows the customer could recognise them. It finds patterns, not names, so a person's name in a column you add with `--allow-columns` is not removed. **Review the output before sharing it**, and follow the [Data Classification Policy](https://connect.cbts.com/redir/44051) for anything customer-owned.

## Privacy modes and sample data

**Privacy.** Every connector that can see people runs in `aggregate` mode by default; `per_user` is an administrator opt-in with a recorded reason, and person identifiers are replaced at ingest by a keyed hash (`privacy.py`), never stored in the clear. Sources that carry prompt or conversation content are never connected. See [ADR 0012](../adr/0012-privacy-modes-for-vendor-sources.md). Only the pseudonymizer exists so far.

**Sample data.** `python -m cfa_tokenomics.samples OUT_DIR [--month 2026-10] [--seed 7] [--identity]` writes a deterministic, fully synthetic set that describes one fictional cast: Example Co, twelve users (`user-0001` to `user-0012` at `example.test`) in three teams, three applications, an AWS sandbox account and an Azure sandbox subscription. It contains an AWS Data Exports tree and an Azure export tree (FOCUS-style CSV gzip, two parts each, with Usage, Tax, Credit, Purchase and Correction rows, tagged and untagged cost, and AI token rows using the FOCUS 1.5 draft's model and token properties), the unified OpenAI Daily Usage API (per user and workspace-wide, credits, USD and tokens kept separate), and the Anthropic usage and cost analytics shapes (by model and by actor, amounts as cents strings). `--identity` adds the 1.5 draft identity columns to the AWS rows so the importer's dropping of them can be tried. Every FOCUS row carries `x_SyntheticSample = true`. **The layouts and shapes follow vendor documentation and have not been checked against a real export or live API**, so these files test the product's assumptions, not the vendors' behaviour. FOCUS cost lines have no user dimension, so the cast's users link to cost only through the team and application tags.

## Manual FOCUS import (implemented)

`python -m cfa_tokenomics.admin import-focus TENANT_ID FILE [--version 1.2] [--final] [--allow-partial]` imports a FOCUS CSV (plain or gzip) through a connector named `manual-focus-import`. It is the first connector and the way to put real cost data into the model before any API connector exists. **Tested on synthetic files only; no real export has been imported.**

- **Parse, don't coerce.** Required columns are the five FOCUS-mandatory ones (`BilledCost`, `EffectiveCost`, `ListCost`, `ContractedCost`, `ChargeCategory`) plus `ChargePeriodStart`, `ChargePeriodEnd` and `BillingCurrency`. A row is rejected, with a reason code, for an unknown `ChargeCategory`, a non-finite or non-numeric amount, an amount with more than 18 decimal places (never rounded), a timestamp without a time zone, a bad currency code, an empty period, or invalid tags. Unrecognized columns (for example Azure's `x_` columns) are kept as extensions.
- **Strict by default.** If any row is rejected the whole file is refused and nothing is imported (the rejects are recorded). A partial import silently drops money, and a later revised export would then replace good earlier rows. `--allow-partial` is explicit consent.
- **Once per file.** The same file content is imported once per connector.
- **Revisions replace, never add.** A revised export supersedes earlier records only for the (billing account, sub account) pairs it contains and only inside the charge-period window it covers; replaced rows stay as history. Different connectors are different sources and never supersede each other. This rule is a working design and **needs checking against real Azure and AWS exports** (partial or filtered exports could behave differently).
- **Finality.** A run is `provisional` until its last charge period ended more than 7 days ago, then `final` (Azure documents changes until the fifth day after period end; Anthropic reports about a week). `--final` overrides.
- **Lineage.** Every record points to its raw file (kept gzip, byte for byte) and its row number. Cost records, raw files, rejects and supersessions are append-only.
- **Version.** The declared FOCUS version (1.0 to 1.5) is recorded but processing is by column name. `ServiceProviderName` is required for declared 1.4 and 1.5 (Mandatory in 1.4). The only legacy mapping is `ProviderName` to `ServiceProviderName` (confirmed from the specification history), recorded in the row when used; `PublisherName` is kept as an extension. See [FOCUS 1.5 readiness](08-focus-1-5-readiness.md).
- **Privacy.** The 1.5 identity columns are not stored in normalized records unless explicitly requested. The raw file is kept as received.
- **Currency.** `BillingCurrency` must be a three-letter code; `PricingCurrency` may be a provider unit (FOCUS 1.5 draft).
- **Not built:** Parquet (Azure and AWS can export it; the cloud connectors below ask for CSV) and automatic version detection.

## AWS and Azure cost-export connectors (implemented)

Two pull connectors read a FOCUS cost export from storage the customer already owns and hand each billing period to the importer above. **Tested on synthetic exports with in-memory stores and stubbed clients; nothing has been run against a real S3 bucket, a real storage account or a real export** (R-27).

```text
python -m cfa_tokenomics.admin connector-add aws|azure TENANT_ID NAME SCOPE.json
python -m cfa_tokenomics.admin connector-check  TENANT_ID NAME      identity, access and data, reported separately
python -m cfa_tokenomics.admin connector-run    TENANT_ID NAME [--dry-run]
python -m cfa_tokenomics.admin connector-status TENANT_ID NAME
```

There is no scheduler yet: `connector-run` is idempotent and safe to run from cron or a job runner.

**Settings** (`SCOPE.json`; any other key is refused):

| Setting | Meaning |
| --- | --- |
| `bucket`, `region` (AWS) | The S3 bucket holding the export, and optionally its region. |
| `account_url`, `container` (Azure) | The bare storage account address and the blob container. A URL with a query string (a SAS token), credentials or a path is refused. |
| `prefix` | Path to the export, above the date folders. AWS: `<prefix>/<export name>`; Azure: `<directory>/<export name>`. |
| `focus_version` | Declared FOCUS version recorded on the run (default `1.2`). Processing is by column name. |
| `lookback_periods` | How many months back to read (1 to 24, default 3). |
| `settle_minutes` | A run whose files changed more recently than this is deferred (default 30), so a half-written export is never read. |
| `max_run_mb` | Uncompressed size cap per run (default 200). |
| `allow_partial` | Import good rows when some are rejected (default false: the whole run is refused). |

**Credentials are never settings.** The connector uses the platform's own identity: an AWS instance, task or SSO role through the default credential chain; an Azure managed identity through the default Azure credential chain. Nothing is stored in the database (`credential_ref` stays empty), logged or passed on a command line. Storage errors are reduced to a class and a fixed message, so a failure cannot echo a role ARN or a signed URL.

### Onboarding checklist

- *AWS.* Create a Data Export in Billing and Cost Management: "FOCUS 1.2 with AWS columns" (or 1.0), format **Text or CSV with GZIP** (not Parquet or zip), to a bucket in the customer's account. Give the runtime role `s3:ListBucket` on the bucket (scoped to the prefix) and `s3:GetObject` on the prefix, and nothing else: the connector reads S3 only and calls no Data Exports or Cost Explorer API. (Standard S3 action names; confirm against the customer's policy tooling.)
- *Azure.* Create a Cost Management export "Cost and usage details (FOCUS)", daily, month to date, format **CSV (none or gzip)** (not Parquet), to a storage account, for an EA or MCA scope (management-group and pay-as-you-go scopes are not supported by Azure's FOCUS export). Give the runtime's managed identity the built-in **Storage Blob Data Reader** role on the container. (Role name not confirmed on the pages read; confirm in the customer's tenant.)
- Run `connector-check`. It reports configuration, access (can the location be listed) and data (is there a run in a supported format) as separate steps, so a failure names the layer to fix.

### How a run is chosen and imported

- A run is the set of files that make up one billing period's export. Both clouds split large exports into several files, and the importer treats each file as a revision that supersedes earlier rows for the same account and window, so **a run's parts are joined into one logical file** (same columns required; different columns refuse the run). Importing parts one by one would have kept only the last.
- Exports are cumulative, so **only the newest run of each period is read**. Older runs of the same period are passed over.
- A run already imported is skipped **without downloading it**. The identity of a run includes each file's etag and size, so an export overwritten in place is seen as new, and the importer's supersession replaces the earlier rows while keeping them as history.
- A run that failed deterministically (a rejected row, mismatched columns) is **not retried until its files change**, and is reported as `failed_before` so it is not silent.
- **Finality** follows each cloud's documented revision window, not one global rule: Azure 7 days after the period ends, AWS 14 days.
- Unreadable formats are reported, not skipped: a Parquet or zip export says to change the export format to CSV.

### Limits, stated plainly

- **Whole runs are held in memory** (default cap 200 MB uncompressed, raised with `max_run_mb`). A larger run is refused as `too_large`, never truncated. Large enterprise exports will exceed this: **streaming import is the next piece of work**, and Parquet support after it.
- **The layouts are from documentation, not a real export.** Matching is tolerant of depth, and nothing depends on a manifest's internal fields (not verified), so completeness is judged by `settle_minutes`, not by a manifest. Whether Azure writes `manifest.json` before or after the data files is unknown.
- **No Cost Explorer or Cost Management API.** These connectors read exports only. Cost Explorer's new Bedrock attributes and Azure's Query API are separate sources ([vendor research](09-vendor-api-research.md)).
- **No scheduler, no health screen, no UI** to add a connector. Status is a command.
- **Do not point two connectors at one export:** supersession is per connector.

## Anthropic connector (implemented, aggregate mode)

Reads the Admin API's usage and cost analytics endpoints (beta) with a read-only credential. **Tested against a fake server built from the documented response shapes and the synthetic sample set; nothing has been run against the real API, so bracket encoding of `group_by[]`, paging and the exact error behaviour are unverified** (R-29).

```text
python -m cfa_tokenomics.admin connector-add anthropic TENANT_ID NAME SCOPE.json
python -m cfa_tokenomics.admin connector-check|connector-run [--dry-run]|connector-status TENANT_ID NAME
```

**Settings** (any other key is refused, so a key has nowhere to go): `credential_ref` (required), `mode` (`aggregate`, the default; `per_user` is **refused: its pseudonymized storage is not built**, [ADR 0012](../adr/0012-privacy-modes-for-vendor-sources.md)), `lookback_days` (1 to 365, default 35), `billing_account_id` (a label for the FOCUS billing account, default `anthropic`).

**The credential is a reference, never a value.** `credential_ref` is `env:NAME` (an environment variable the deployment fills from the customer's secret store) or `file:/absolute/path` (a mounted secret file). It is stored in the connector's `credential_ref` column, resolved only when a request is made, and never logged, echoed in an error or placed in settings. The API host is fixed in code (`https://api.anthropic.com`), so a key can only be sent there. Use an Admin API key (Console), or an Analytics key with `read:analytics` (Claude Enterprise); workspace-scoped keys do not work.

### What a run does

- Reads whole UTC days up to the start of today, in windows of at most 31 days, grouping only by `model`, `workspace_id`, `service_tier`, `speed` and `context_window`. It **never groups by `actor`**, and refuses (storing nothing) any row that carries person-level fields anyway.
- Requests are paced under the documented 60 per minute, retried a bounded number of times (honoring `Retry-After`), and a cursor that expires because the data was refreshed restarts the query. An unexpected response shape is an error, not a guess.
- **Usage** goes to the usage ledger as `anthropic` observations from the `vendor_admin_api` source: `input` is Anthropic's *uncached* input, cache reads and writes keep their own categories (writes are the 5-minute plus 1-hour counts), `total` is the source's total. They are summed over tier, speed and context window because the ledger has no such dimensions.
- **Cost** goes in as FOCUS-shaped rows through the FOCUS importer, so it has lineage, revision handling and finality. `amount` (after discounts, before credits) fills BilledCost, EffectiveCost and ContractedCost; `list_amount` fills ListCost; cents are converted to dollars exactly. Token counts are joined from the usage rows of the same group, so cost per million tokens works in the [AI token view](08-focus-1-5-readiness.md); `SkuPriceDetails` carries `ModelDeveloper`, `ModelId`, `TokenDirection` and `TokenCacheAction` (uncached, read, write).
- **Days newer than the response's `data_refreshed_at` are left for a later run**, because they are partial or missing. Finality is `provisional` until about 7 days after month end, then `final`.
- An unchanged window is not imported again; a revised one supersedes the earlier rows and keeps them as history.

### Anthropic connector limits

- **`BilledCost` is not the invoiced amount.** Credits are not visible in this API, so it is the pre-credit amount; each row says so (`x_BilledCostIsPreCredit`), and the invoice stays authoritative. Priority Tier commitment fees are not in this data, and neither is usage through Bedrock, Vertex or Foundry (that is in the cloud bill).
- Aggregate mode only: no per-person usage, no Claude Code per-user analytics, no spend-limit or member endpoints.
- No scheduler, no health screen, no UI to add a connector. `connector-run` is idempotent and safe to run from cron.
- Cost types other than tokens (web search, code execution, session usage) are stored as cost with no token quantity.

## Codex and ChatGPT Enterprise connector (implemented, aggregate mode)

Reads the unified Daily Usage API with `group=workspace`, using a read-only Admin key. **Tested against a fake server built from the vendor's OpenAPI schema and the synthetic sample set; nothing has been run against the real API** (R-30).

```text
python -m cfa_tokenomics.admin connector-add openai_codex TENANT_ID NAME SCOPE.json
python -m cfa_tokenomics.admin connector-check|connector-run [--dry-run]|connector-status TENANT_ID NAME
```

**Settings:** `credential_ref` (`env:` or `file:`, as for the [Anthropic connector](#anthropic-connector-implemented-aggregate-mode)), `workspace_id` (required), `mode` (`aggregate`; `per_user` is refused until its storage exists), `lookback_days` (default 35), `final_after_days` (default 30, 7 to 90) and `billing_account_id`. The host `https://api.chatgpt.com/v1` is fixed in code. The key needs the `enterprise.analytics.usage` read scope.

### How Codex cost is stored

- **Credits and native USD are separate in the source and are never converted here.**
- **Native USD** usage (`cost_usd`) is stored as cost with basis `observed`: the vendor reports it, though the API says it is not a final invoice amount. Its SubAccountId is `<workspace>:usd`.
- **Credit-priced usage** is stored as cost only where the source gives `estimated_cost_usd`, which the API defines as an estimate at the workspace's *current credit overage rate*. It is stored with basis **`estimated`**, never `observed`, with the exact credits kept in `x_Credits`. Its SubAccountId is `<workspace>:credits`. Credits with no estimate are counted and left unpriced.
- The two streams have different SubAccountIds so that one being revised never supersedes the other.
- What the day's totals hold beyond the model rows is kept as an unattributed slice, so the model breakdown never understates a day.
- **Text tokens** exist only for API-priced usage. They go to the usage ledger as `openai_codex` observations (`input` is uncached input, `cache_read` is cached input) where the source gave them. A missing field is unknown and produces nothing; a reported zero stays zero.
- Amounts arrive as JSON numbers, so the client parses them straight into exact decimals, never through a float.
- Activity counts (chats, messages) are not stored: the ledger holds token categories only.

### Codex connector limits

- **The correction window is unknown.** The API says recent rows may be corrected and gives no window, so cost is `provisional` until `final_after_days` after the **window's** last day (30 by default, an assumption). Finality comes from the window, not from each file's own latest day, so the two streams agree.
- Today is never read: it is still being filled.
- Aggregate mode only: no per-user rows, no per-user monthly usage or spend-cap endpoints, no plugin, skill or tool detail, and the Compliance API is never connected.
- The credit estimate uses the workspace's *current* rate, so it can move when the rate changes; the credits themselves are exact and kept.
- No scheduler, no health screen, no UI.

## Capability matrix

`Tokens` means token counts by category. `Cost` means a dollar amount from the source. `Seats` means seat or licence data.

| Source | Tokens | Other usage | Cost | Seats and licences | Authority for cost |
| --- | --- | --- | --- | --- | --- |
| **AWS Data Exports (CUR 2.0 and FOCUS)** | no (usage amounts in billing lines) | resource and usage lines | **yes, billed** | no | **Billed cost** for AWS services including Bedrock |
| **AWS Bedrock CloudWatch** | **yes** | invocations, latency, errors, throttles | no | no | none (usage driver) |
| **AWS Bedrock invocation logs** | **yes, per request** | requests | no (cost is an estimate from tokens and your rate card) | no | none; **contains full bodies** |
| **AWS Cost Explorer API** | no | cost by dimension | yes | no | not established: granularity, history and pricing **not found** |
| **Azure Cost Management export (FOCUS)** | no | usage lines | **yes, billed and amortized** | no | **Billed cost** for Azure services |
| **Azure OpenAI / Foundry metrics** | **yes** | requests | `FoundryModelEstimatedCost` is an **estimate (preview)** | no | none; estimate only |
| **Anthropic Usage and Cost Analytics API** | **yes** | requests | **yes** (`amount`, `list_amount`) | no | Vendor cost, when billed by Anthropic |
| **Anthropic Claude Code Analytics API** | **yes** | sessions, accepts, commits, PRs | `estimated_cost` | no | none (estimate) |
| **GitHub Copilot usage metrics** | partial (CLI, app, BYOK fields) (summary) | interactions, active users, acceptances | no | no | none |
| **GitHub Copilot seats and billing** | no | AI credits (premium requests were replaced on 2026-06-01) | **yes** (`netAmount` etc.) | **yes** (seats, plan, last activity) | **Billed cost** from GitHub |
| **Microsoft 365 Copilot (Graph reports)** | **no** | active users, prompt counts, per-app last activity | **no** | licensed users only; licensing via Graph | none |
| **Microsoft Graph licensing** | no | no | no | **yes** (`consumedUnits`, per-user license details) | none (needs a licence price) |
| **OpenAI Usage and Costs API** | **yes** | requests | **yes** (daily only) | no | Vendor cost |
| **OpenAI Codex and ChatGPT Enterprise (Daily Usage API)** | **text tokens for API-priced usage only** (uncached, cached, output) | daily chats, messages, plugins, skills, tools | **credits and native USD, kept separate** (plus an estimate of the credit part); not an invoice | per-user monthly usage against caps (PII) | credits or USD as reported; Codex with an API key is in the OpenAI costs API |
| **Google Gemini and Vertex AI** | Vertex: token metrics in Cloud Monitoring (beta). Gemini Developer API: per response only, no org API found | n/a | via Cloud Billing | no | Cloud Billing BigQuery export (a FOCUS export is in preview) |
| **Perplexity** | per response only; no org API found | console only | console only | no | not established |
| **Application and gateway telemetry** | **yes, per request** (if instrumented) | requests, sessions, users | no | no | none |
| **Manual import** | as supplied | as supplied | as supplied | as supplied | as supplied |

### Source notes

The notes below were the first reading. The later, fuller research (nine vendors, with sources, permissions, limits, privacy flags and the items still not found) is in [vendor API research](09-vendor-api-research.md); where the two differ, **that document is current**. Its main corrections: Claude in Azure Foundry is billed through one Marketplace consumption-unit meter; third-party Bedrock models are billed under the model provider, not under Bedrock; GitHub replaced premium requests with AI credits and retired its legacy metrics APIs; OpenAI cost amounts are JSON numbers, not strings; and Microsoft Copilot reports now exist under `/copilot/reports` in v1.0.

**Anthropic.** Current API is in beta: `GET /v1/organizations/analytics/usage` and `.../analytics/cost` with the header `anthropic-beta: analytics-usage-cost-2026-08-24`; a legacy `usage_report/messages` endpoint is still documented. Auth is an Admin API key or an OAuth token with the `org:admin` scope (Console organizations), or a key with the `read:analytics` scope (Claude Enterprise); unavailable to individual accounts. Token categories: uncached input, cache creation (5-minute and 1-hour), cache read, output, total, plus requests and web-search requests. Dimensions: model, workspace, API key, actor (user, service account or key), service tier, context window, inference geography, speed, product; up to five `group_by` values. Buckets `1m`, `1h`, `1d`; at most 31 days per request. Cost amounts are **decimal strings in cents with six decimals** (parse as decimal, never float), always USD. Data typically refreshes within 4 hours and can take up to 24; values can be revised until about 7 days after month end; responses carry `data_refreshed_at`. Claude Code Analytics (`/v1/organizations/usage_report/claude_code`) is one UTC day per request, includes user email, and **does not return subscription-plan usage** (Pro, Max, Team, Enterprise); only usage authenticated against the Console organization. (<https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api>, <.../claude-code-analytics-api>)

**GitHub Copilot.** Usage-metrics report endpoints exist at enterprise and organization level (`.../copilot/metrics/reports/...`, 1-day and 28-day, by users, repos, teams); responses are download links to signed report files; the enterprise policy "Copilot usage metrics" must be enabled; history from 2025-10-10 up to one year. Seat endpoints (`/orgs/{org}/copilot/billing`, `.../billing/seats`) return seat counts, plan type and last activity (owners only). Billing endpoints (`/organizations/{org}/settings/billing/premium_request/usage`, `.../ai_credit/usage`, `.../usage`) return product, SKU, model, unit type, price per unit, gross and net amounts; org administrator required; last 24 months. No dollar-cost field in the metrics reports; token fields only in some CLI and app breakdowns (summary). (<https://docs.github.com/en/rest/copilot/copilot-usage>, `.../copilot-user-management`, `.../billing/usage`)

**Microsoft 365 Copilot.** Graph function `getMicrosoft365CopilotUsageUserDetail` (path `GET /v1.0/copilot/reports/...(period='D7')`; periods D7 to D180 and ALL) returns per-user last-activity dates per app and, in v2, prompt counts and active usage days; CSV or JSON; **licensed Copilot users only**; permission `Reports.Read.All`. **No tokens and no cost.** By default user-identifying fields are hidden in usage reports; data appears within about 48 hours. Licensing: `GET /subscribedSkus` (`consumedUnits`, `prepaidUnits`) and `GET /users/{id}/licenseDetails`, permission `LicenseAssignment.Read.All`. The Copilot SKU name and the Viva Insights Copilot Dashboard were **not read**. (<https://learn.microsoft.com/en-us/graph/api/reportroot-getmicrosoft365copilotusageuserdetail?view=graph-rest-beta>, `.../subscribedsku-list`)

**Azure.** Cost Management exports include "Cost and usage details (FOCUS)" (documented as 1.2-preview) for EA and MCA scopes; management-group scope is not supported; delivery to a storage account as CSV or Parquet with a manifest per run; typically available within 4 hours of a run, with charges changing until the fifth day after period end and rerating until invoice close. About 52 `x_` Azure-specific columns. RBAC: Cost Management Reader (view), Cost Management Contributor (create exports; "recommended least privilege role"), plus Storage Account Contributor for export storage; Monitoring Reader for metrics. Azure OpenAI metrics: `ProcessedPromptTokens`, `GeneratedTokens`, `TokenTransaction`, `InputTokens`, `OutputTokens`, `TotalTokens`, `AzureOpenAIRequests`, cache and PTU metrics; dimensions include deployment, model, version, region; 1-minute grain. `FoundryModelEstimatedCost` is explicitly "an estimate and is not an invoice or billed charge". **No documented join between token metrics and Cost Management rows** other than shared resource tags. Numeric API rate limits were **not found**. (<https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports>, `.../dataset-schema/cost-usage-details-focus`, `.../foundry-classic/openai/monitor-openai-reference`)

**AWS.** Data Exports offers "FOCUS 1.2 with AWS columns", "FOCUS 1.0 with AWS columns" and CUR 2.0 to S3 (ZIP, GZIP, Parquet); finest grain is per usage type per day. Bedrock publishes CloudWatch metrics in `AWS/Bedrock`: `Invocations`, `InputTokenCount`, `OutputTokenCount`, `CacheReadInputTokenCount`, `CacheWriteInputTokenCount`, latency, error and throttle metrics, `EstimatedTPMQuotaUsage` (an approximation; "do not use as the sole indicator"), dimension `ModelId`. **Invocation logging** is off by default and records, per request, `accountId`, `region`, `requestId`, `modelId`, `identity.arn`, `inputTokenCount`, `outputTokenCount`, `requestMetadata`, and **full input and output bodies** (up to 100 KB). **Attribution:** application inference profiles carry tags that flow to Cost Explorer and CUR once activated as cost allocation tags (up to 24 hours; not retroactive); per-request metadata appears only in invocation logs and **not** in Cost Explorer or CUR, so cost derived from logs is an estimate. Latency and restatement behaviour of Data Exports, CloudWatch and logs were **not found**. (<https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring-runtime-metrics.html>, `.../model-invocation-logging.html`, `.../cost-mgmt-application-inference-profiles.html`, `.../cost-mgmt-request-metadata.html`)

**OpenAI.** Organization usage endpoints (`/organization/usage/completions`, `/embeddings`, `/images`, and others) and `/organization/costs`, authenticated with an admin key. Completions report `input_tokens` ("including cached and cache-write tokens"), `output_tokens`, `input_cached_tokens`, `input_uncached_tokens`, `input_cache_write_tokens`, request counts; grouping by project, user, API key, model, batch, service tier. Buckets `1m`, `1h`, `1d`. Costs: daily buckets only (summary). Data delay and retention **not found**. Codex: a daily usage Analytics API exists for ChatGPT and Codex workspaces and requires a workspace-scoped admin key with a specific scope; its endpoints and fields were **not read**. (<https://developers.openai.com/api/reference/resources/organization/subresources/usage>)

**Google Gemini and Perplexity.** Gemini returns per-response `usageMetadata` (prompt, cached content, candidates, tool use, thoughts, total; `promptTokenCount` **includes** cached tokens). No organization usage API was found in the pages read; costs are in Cloud Billing, which can lag about a day. Perplexity documents an admin-only console usage page and a per-response `usage.cost.total_cost`; **no organization usage API was found**. Vertex AI, Cloud Billing export and Cloud Monitoring were **not read**.

## Consequences for the design

- **Cost authority belongs to billing sources**, not usage sources. Bedrock and Azure OpenAI tokens *explain and allocate* cost that arrives in CUR or the Azure FOCUS export. Estimates from tokens times a rate card are `estimated` and never replace billed cost ([overlap resolution](05-calculation-engine.md#10-overlap-resolution)).
- **Where the product is the bill, use the vendor's cost.** Anthropic and OpenAI cost endpoints are observed vendor cost, *unless* the model is bought through a cloud marketplace, in which case the cloud invoice is the billing owner.
- **Subscriptions have cost without tokens.** Copilot seats cost `seats × price` (billing API, invoice import or price book) and report activity, not tokens. Their unit economics are per seat, per active user or per prompt. The UI shows tokens as "not reported", never zero.
- **Allocation needs tags.** Azure resource tags, AWS cost allocation tags and Bedrock application inference profiles are the documented attribution routes; per-request metadata is estimate-only. The product recommends tagging conventions and reports allocation coverage.
- **Privacy by design.** Several sources return per-user data (Anthropic actor email, GitHub per-user reports, M365 per-user rows) and Bedrock logs hold prompt bodies. Defaults: ingest aggregates, pseudonymize user references, never ingest bodies, and put retention on every layer. This is risk R-17.
- **Versions and revisions differ per source**, so facts carry `finality` and the FOCUS source version.

## Adding a provider

1. Read the vendor's documentation; fill a manifest and record anything *not found* as unknown.
2. Write sanitized fixtures from documented responses (never customer data).
3. Implement `pull` and a pure mapper; set `basis` and `finality`.
4. Contract tests: idempotent window, cursor safety, partial data, mapper determinism, no secret or body in raw or logs.
5. Document required permissions and the onboarding checklist.
6. An authorized integration test in a customer or test account before the connector is marked supported.

No provider requires a schema or business-logic change.
