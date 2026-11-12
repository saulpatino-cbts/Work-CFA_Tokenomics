# 1. Current-state assessment and gap analysis

**Status:** proposed assessment, written 2026-11-07 against `main` at the time of writing. It treats the existing application as a prototype, not a specification. Part of the [AI economics redesign](README.md).

## A. What the application is today

The repository holds a documentation set and an early implementation (`apps/api`, `apps/web`). It was designed around one question: **"How many tokens did this AI workload consume, and can we trust the number?"**

What exists, and what it was built to do:

| Area | What is built | Evidence |
| --- | --- | --- |
| Identity and access | OIDC bearer verification, group-to-role mapping (admin, finance viewer; ADR 0013), bootstrap admin, last-admin protection, per-identity account grants, audit events | `auth.py`, `authz.py`, `roles.py`, `scope.py`, migrations 0001, 0003 |
| Usage ledger | `usage_request_observations` (one row per model call routed through the app), `usage_aggregate_observations` (provider metric windows), collection checkpoints; idempotent writes; `sku` and `source_type` dimensions | `db.py`, `usage/ledger.py`, migrations 0002, 0004 |
| Reconciliation | Rules for comparing app-routed requests with a provider aggregate without adding them (`app_only`, `provider_only`, `reconciled`, `app_exceeds_provider`) | `usage/reconcile.py`, ADR 0007 |
| Read APIs | `GET /v1/usage` (reconciled rows), `GET /v1/usage/series` (bucketed, one token category per query) | `usage/query.py`, `usage/series.py` |
| Connector | A Bedrock CloudWatch metric normalizer and a one-method `AggregateCollector` protocol. No live call, no credentials, no scheduler | `providers/` |
| Web app | A telemetry page: token counters, hourly series by vendor and SKU, heatmap, freshness, reconciliation table. Browser sign-in written but never tested against a real identity provider | `apps/web` |
| Delivery | Multi-stage container, CI with PostgreSQL, security headers, Alembic migrations | `Dockerfile`, `api-ci.yml` |
| Documents | Requirements, 10 ADRs, risk register, marketplace gap analysis, UI concepts | `docs/` |

Everything in it is tested against synthetic data only. There is no connector that has touched a real provider, no price, no cost, and no concept of an application.

## B. Gap analysis

The target is an economics platform: usage becomes cost, cost becomes application cost, application cost meets business value, and that yields unit economics, a price and a margin. The current design stops at the first arrow.

| # | Gap | Why it blocks the vision | Where it shows in the code |
| --- | --- | --- | --- |
| G1 | **No Application / AI Solution entity.** The unit of analysis is `(provider, account, model)`. | The target's primary unit is the application. Nothing can be aggregated, allocated or compared per application, customer, team or environment. | `db.py`: no `application`, `workload`, `customer`, `team` |
| G2 | **No cost at all.** No price book, no billed cost, no FOCUS record, no cloud resource. | Cost is half of the headline sentence. Tokens cannot be turned into dollars, and cloud, licence and labour costs have nowhere to live. | No cost table; `value` columns are token counts |
| G3 | **The ledger is token-shaped.** Categories are fixed to input, output, cache, reasoning. | Many enterprise products expose only requests, sessions, seats or billing. The target needs one normalized model for measurements of any type. | `usage/models.py` `CATEGORIES` |
| G4 | **Quality is not basis.** `reported / estimated / partial / unknown` describes completeness, not whether a number is observed, estimated or an assumption. | The brief requires every figure to be labelled observed, estimated or user-entered, and never to present an estimate as telemetry. | `Quality` enum |
| G5 | **Provenance is shallow.** Rows carry a source key, normalization version and revision, but no link back to the raw record, ingestion run, price version or calculation. | The target asks for number, calculation, input, source and timestamp for every important figure. | No raw landing zone, no lineage |
| G6 | **Money is stored as floating point.** | Financial figures that justify commercial decisions need exact decimals and a stated currency and rate source. | `Float` in `AggregateObservationRow.value` |
| G7 | **No business value, scenario or pricing engine.** | These are the product. Without them the platform cannot state ROI, payback, unit economics, a required price or a margin. | Absent |
| G8 | **Single-tenant by construction.** No `tenant_id` anywhere. | The brief asks for tenant isolation. Retrofitting it later touches every table and query. | All tables |
| G9 | **Connector contract is too narrow.** One method returning aggregate token observations. | Connectors must also pull cost exports, seat and licence data and resources, land raw data first, and declare what they can and cannot measure. | `providers/base.py` |
| G10 | **Reconciliation is specific, not general.** It compares two sources for token counts only. | The same overlap problem exists for cost (cloud invoice versus vendor invoice, or Claude on Bedrock versus Anthropic's own API). It needs to become a general overlap-resolution step. | `usage/reconcile.py` |
| G11 | **The UX leads with tokens.** The home screen is token counters and a per-hour chart. | Executives need spend, causes, applications, value, ROI and price first. Tokens should sit underneath. | `apps/web/src/pages/Telemetry.tsx` |
| G12 | **Scope documents conflict with the target.** REQ-012 excludes "commercial operations"; ADR 0003 names three providers; the roadmap defers forecasting, budgeting and cost projection. | The owner now wants pricing and marketplace economics modelling and a wider source list. The documents must be reconciled explicitly, not silently contradicted. | `requirements.md`, ADR 0003, `roadmap.md` |

## C. Classification of existing capabilities

**KEEP** means it correctly supports the target. **REFACTOR** means the capability is useful but sits on the wrong model. **REMOVE** means it does not contribute to the target. **BUILD** means it is missing.

### KEEP

| Capability | Reason |
| --- | --- |
| Customer-hosted boundary, no vendor data plane, customer-held credentials (ADR 0001) | Matches the security requirement. See the tenancy question in the [README](README.md#decisions-needed). |
| OIDC verification, role model, audit events, last-admin protection | SSO, RBAC and audit logging are explicit requirements. Reusable as written. |
| Principles: unknown is not zero; sources are never added across overlap; deny by default | These generalize directly to cost and value. They are the product's integrity rules. |
| PostgreSQL plus Alembic migrations; replay-safe writes; checkpoints advanced only after durable writes | Sound foundation for ingestion traceability. |
| Secret handling by reference, config validation, security headers, same-origin web serving | Matches the enterprise security requirement. |
| Container packaging and marketplace delivery plan (ADR 0005), CI | Needed for the commercial story. |
| Web shell, brand tokens, sign-in code | Reusable infrastructure; screens change. |

### REFACTOR

| Capability | Change needed |
| --- | --- |
| `usage_request_observations` and `usage_aggregate_observations` | Become the **raw and normalized usage layers**. Generalize to measurement types beyond tokens, add `tenant_id`, `basis`, `raw_record_id`, exact decimals. |
| `sku` and `source_type` | Fold into a proper charge and pricing model (SKU, pricing category, commitment) aligned to FOCUS. |
| `reconcile.py` | Generalize into an overlap-resolution service that works on any measure and on cost. |
| `AccountGrant` and the scope check | Re-scope to Tenant, Application, Business Unit, Environment. |
| `GET /v1/usage/series` and `/v1/usage` | Become one analytics API over normalized facts, with provenance returned alongside values. |
| `providers/base.py`, Bedrock normalizer | Become the connector framework (manifest, capabilities, raw landing, versioned mapper). The Bedrock mapping is a useful first mapper. |
| Telemetry page | Demote to a drill-down beneath application economics. |
| Audit events | Extend to cover assumption edits, scenario changes, price-model changes and exports. |

### REMOVE (from the baseline scope)

| Item | Reason |
| --- | --- |
| The token-counter-first dashboard concept and the token-provider-centric setup wizard concept in `design/concepts` | They encode the wrong product. Replace with the screens in [UX](06-ux.md). The files stay in history. |
| The "three cloud providers only" framing (ADR 0003, [providers](../providers.md)) | Superseded by the connector framework and the wider source list. |
| Vendor Assessment access as a near-term feature ([assessment](../assessment.md)) | Not on the path to the target. Keep the no-standing-vendor-access principle; defer the feature. |
| Treating token observation mode as the central design decision (ADR 0007's framing) | The reconciliation rules survive as overlap resolution; the framing as "observation mode" does not. |

### BUILD

Application model; FOCUS-aligned cost layer; price books; allocation and tagging; cloud resource model; business metrics and value assumptions; business value engine; scenario and forecast engine; sensitivity analysis; commercial pricing and marketplace economics; provenance and explain API; connector framework with manual import; tenant isolation (row-level security); connector health monitoring; retention controls; executive dashboards and reports; exports and APIs.

## D. What this means

Roughly the identity, security, delivery and ingestion plumbing is reusable. The data model, the API surface and the entire front-end story change. The most important single design decision is that **a normalized fact, not a token count, is the unit of storage**, and every fact carries its basis, source and lineage from the moment it is ingested.
