# 7. Delivery roadmap

**Status:** proposed. Part of the [AI economics redesign](README.md). Phases are ordered so that each one delivers something usable on **real data**, and so manual import makes Phase 1 useful before any connector exists. Nothing here is committed to dates.

## Cross-cutting rules

- `tenant_id` and row-level security from the first new table, even though a customer-hosted install has one tenant.
- Exact decimals and currency everywhere new.
- `basis` and `finality` on every new fact; lineage columns from day one.
- No new token-only features. Existing telemetry stays working while the new model is built beside it.
- Each phase has a demonstration on non-synthetic data supplied by a customer or the owner.

## Phase 1 progress

| Slice | State |
| --- | --- |
| 1. Calculation library (`apps/api/src/cfa_tokenomics/econ`): exact decimals, basis and provenance nodes, cost, value, ROI, payback, unit economics, scenarios, sensitivity, pricing and margin | **Done** (tests, synthetic inputs) |
| 2. Data model with `tenant_id` and row-level security; application, workload, price book, assumptions, scenarios, calculation nodes | **Done** for the new tables (migration 0005, repository, tests on a restricted role). Not wired to API routes yet (slice 5). The legacy tables were isolated in slice 7. |
| 3. FOCUS 1.4 cost schema, version upgrade and manual import connector | **Done for CSV** on synthetic files (migration 0006, parser, importer, `import-focus` command). **Not validated on a real export.** No Parquet. The 1.0 to 1.2 column upgrade is only the one alias noted in the data model. |
| 4. Allocation engine and allocation coverage | **Done** on synthetic cost lines (migration 0007, pure engine, runner, reports, `allocate` command). Drivers are entered, not derived from usage. Not validated on real exports. |
| 5. API for applications, assumptions, scenarios and the explain view | **Done** (`economics_api.py`, 15 tests on a restricted role, synthetic data). Reads need `economics:read`, writes `economics:write`. No per-application scoping (R-25). No screens (slice 6). |
| 6. Application economics screens | **Done** for the application core (`apps/web`): portfolio, application detail with Economics, Value model, Cost and allocation (tenant-wide coverage) and the existing telemetry as the Usage tab, and the Explain drawer. 39 web tests plus a check against the real API on synthetic data. No scenario studio, pricing studio or FinOps workbench. Brand, fonts and logo still pending approval. |
| 7. Migration of the existing ledger into normalized usage facts | **Done** (migrations `0008` and `0009`, `assign-legacy-tenant` and `project-usage` commands, 36 new tests including a non-superuser owner). Legacy tables are tenant-isolated; `usage_facts` is built from the ledger. Not run against a real install with data; facts are not refreshed automatically and nothing reads them yet. |

Acceptance criteria status (see below): criterion 4 (worked example reproduces exactly) and the engine half of criterion 5 (scenario recalculation, tornado) are met by tests on synthetic inputs; criterion 6 (a cross-tenant read fails at the database) is met for every tenant table, including the former legacy ones; criterion 7 (no floating-point money) holds for the new library and tables; the legacy ledger holds token counts, not money, and its float column is kept with an exact decimal copy in `usage_facts`. Criterion 1 (import a real FOCUS export and see cost allocated to an application) is **partly met**: import and allocation work on synthetic files and the allocated-plus-unallocated total equals the line amount in every measure (tested, including a randomised check), but **no real export has been used**. Criterion 2 (explain view) is **met at the API level**: every figure returned by scenario evaluation carries a node id, and `GET /v1/explain/{node_id}` returns the verified tree down to the inputs and their basis; no screen shows it yet. Criterion 3 (an observed bill replaces an estimate, with the variance shown) is **unmet**: nothing yet compares estimated and observed cost. Criterion 1 additionally needs a real FOCUS export, which has not been supplied.

## Phase 1: Economics foundation

### Scope

- Application, Workload, Business Unit, Customer and Environment model.
- Price book and the token and AI cost model (`AICost` from usage and prices).
- FOCUS 1.4 cost schema, with upgrade from 1.0 to 1.2 inputs, and the **manual import connector** for FOCUS files, generic CSV and price sheets.
- Allocation engine (tag, direct, proportional, fixed, even) with the unallocated bucket and allocation coverage.
- Total Cost of Application, unit economics, business value model with editable assumptions, ROI and payback.
- Scenario engine (Baseline, Current, Forecast, Optimized) and one-at-a-time sensitivity.
- Calculation nodes and the explain view for the headline figures.
- Migration of the existing ledger into normalized usage facts (additive, old tables kept).

### Dependencies

owner decisions in the [README](README.md#decisions-needed); sample real data (an Azure or AWS FOCUS export and an AI vendor usage file); ADR 0011 accepted.

### Acceptance criteria

1. Import a real FOCUS export and see cost allocated to a named application, with `sum(allocated) + unallocated = line amount` verified by test.
2. Every headline figure opens an explain view reaching raw records and showing its basis mix.
3. An estimated cost is never labelled observed; an observed bill replaces the estimate, and the variance is shown.
4. The worked example in the [calculation engine](05-calculation-engine.md#worked-example-illustrative-figures) reproduces exactly in tests, including capacity versus cashable and payback on run cost.
5. A scenario changing users, tokens and model recalculates cost, unit cost, value and ROI, and a tornado ranks the drivers.
6. A cross-tenant read fails at the database in tests.
7. No floating-point money in new tables.

## Phase 2: Real telemetry

### Scope

Connectors, in order of value and ease, each behind the framework in [connectors](04-connectors.md):

1. Azure Cost Management FOCUS export and AWS Data Exports (FOCUS or CUR 2.0): cost authority.
2. Anthropic Usage and Cost Analytics (and Claude Code analytics).
3. AWS Bedrock CloudWatch metrics and Azure OpenAI/Foundry metrics: usage drivers and allocation.
4. GitHub Copilot seats, billing and metrics.
5. Microsoft 365 Copilot (Graph reports and licensing).
6. OpenAI usage and costs; Gemini and Perplexity as their documentation allows.
7. Application and gateway telemetry.

Progress: the **AWS and Azure cost-export connectors are built** ([connectors](04-connectors.md#aws-and-azure-cost-export-connectors-implemented)) on synthetic exports only, with no scheduler, no streaming import and no Parquet; the other connectors below are not started.

Research status: the [vendor API research](09-vendor-api-research.md) (2026-11-10) fills in permissions, limits, revision windows and privacy flags for every source below, and lists what is still not found. Perplexity and the Gemini Developer API have no organization usage API in the pages read, so they stay manual import or gateway telemetry. Codex now has a documented route (the unified Daily Usage API; the Codex-only endpoint retires 2026-12-15). Microsoft 365 Copilot has no dollar cost API.

Also: overlap resolution across sources, connector health and drift monitoring, `finality` handling, privacy defaults (aggregate, pseudonymize, no bodies), tag-coverage guidance, retention controls.

### Dependencies

Phase 1; credentials and an authorized account per source; per-source verification of items marked *not found*; the privacy review (R-17) before any per-user source.

### Acceptance criteria

1. Each connector passes the contract tests and an authorized integration test in a real account before it is marked supported.
2. Re-mapping history from raw reproduces the same facts (mapper determinism test).
3. The same charge from two sources appears once in totals, with the loser kept as variance.
4. Provisional figures are marked and become final after the source's revision window.
5. A connector with revoked credentials shows unhealthy within one schedule interval and loses no data on recovery.
6. No credential, prompt body or user name appears in raw landing, logs or exports under the default settings.

## Phase 3: Commercialization

### Scope

Price models (subscription, per user, usage, per transaction, token-based, application, tiered, customer-specific); required price for a target margin; break-even; margin analysis; marketplace fee schedules and commitment-drawdown settings as configuration; Customer Proposal scenarios and export; monte-carlo sensitivity (optional).

### Dependencies

Phase 1 cost and scenario engines; real marketplace terms entered by the user; ADR 0011 resolving how this relates to REQ-012.

### Acceptance criteria

1. Required-price results satisfy the margin identity in tests, and infeasible cases (`1 - f - m <= 0`) are reported, not computed.
2. Changing a fee schedule changes margin with no code change.
3. A Customer Proposal reproduces from stored inputs, and every number traces through the explain view.
4. Tiered pricing matches hand-calculated graduated tiers in tests.

## Phase 4: Enterprise productization

### Scope

Multi-tenant operation (if chosen), full RBAC with finance and executive roles and scoping to business unit and application, SSO hardening (including a tested real-IdP flow), governance (budgets, approvals), reporting and exports, public API, retention and legal hold, audit completeness, operational controls (backup and restore tests, upgrade runbooks), marketplace packaging and security review.

### Dependencies

Phases 1 to 3; the tenancy decision; a real identity provider for testing; marketplace seller accounts.

### Acceptance criteria

1. Tenant isolation, role denial and scope denial are covered by negative tests at API and database level.
2. Sign-in is tested against a real identity provider.
3. Backup, restore and upgrade are exercised end to end with a documented recovery result.
4. Audit covers sign-in, role, grant, connector, assumption, scenario, price-model and export events.
5. The container image is scanned, has an SBOM, is signed, and base images are pinned by digest.
6. Accessibility review of core screens is completed.

## What stops now

New token-only dashboards, the token-provider-centric setup wizard, and vendor Assessment access are paused. The ledger, identity, scoping, audit, packaging and CI work continues to be reused.
