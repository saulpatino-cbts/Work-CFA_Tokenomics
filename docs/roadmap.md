# Delivery roadmap

## Current status

*Refreshed 2026-11-12 from the changelog, ADRs and risk register. No tests or builds were re-run for this refresh.*

The repository began as a governance/security template and is now an early implementation: an API (`apps/api`) and a web app (`apps/web`) exist. All behaviour is tested on synthetic data only. Nothing has run against a real identity provider, vendor API, cloud export or install with data. No production release or deployment command exists.

| Area | Status | Next evidence |
| --- | --- | --- |
| Product boundaries | Documented; the product is admin-only (ADR 0013) | Owner review of requirements and ADRs. |
| Roles and identity | Implemented: `admin` and `finance_viewer` (ADR 0013, breaking change from `user` and `reader`), OIDC verification, IdP group mapping, audit log. Not tested against a real IdP. | Real-IdP test (Entra ID first, Google Workspace second); directory sync not built. |
| Assessment lifecycle | Proposed detailed contract; not built | Scope approval, transport ADR (R-02), negative tests. |
| Runtime and hosting | Accepted (ADRs 0004-0006); multi-stage container image and CI exist | Install templates and a tested fresh install. |
| Tenancy and data isolation | Implemented: forced row-level security on every table, legacy tables isolated (migrations 0005 to 0009). Not run on a real install with data (R-26). Per-application scoping missing (R-25). | Rehearsal on a copy of a real install; scoping ADR and denial tests. |
| Economics engine (ADR 0011, accepted) | Phase 1 slices 1 to 7 done on synthetic data: exact-decimal calculation library, application data model, FOCUS CSV import, allocation, economics API with explain view, screens, usage facts. See [economics roadmap](economics/07-roadmap.md). | A real FOCUS export imported and allocated; estimate-versus-observed variance (unmet). |
| Cost sources | AWS Data Exports and Azure Cost Management export connectors built against stubbed storage (R-27). Manual FOCUS CSV import works; no Parquet or streaming. | An authorized run against a real export from each cloud. |
| Vendor and Gen AI sources (ADR 0010, 0012) | Anthropic and Codex/ChatGPT Enterprise connectors built in aggregate mode against fake servers (R-29, R-30). Vendor API research documented. Not built: Perplexity, Gemini, GitHub Copilot, Microsoft Copilot via Graph and Viva, per-user mode. | An authorized run per connector; close the *not found* items in the research note. |
| Privacy | Pseudonymizer, per-tenant pseudonym/name display setting and people mapping built (ADR 0012, 0013). Raw FOCUS copy still keeps the 1.5 identity columns (R-17). Retention open. | Customer privacy review; decision on the raw copy and on retention. |
| FOCUS 1.5 / AI token view | `GET /v1/cost/ai-tokens` built from an unratified working draft (R-20, R-28). Ratification is scheduled for 2026-12-03. | December checklist in [FOCUS 1.5 readiness](economics/08-focus-1-5-readiness.md). |
| Web app | Portfolio, application detail, explain drawer and telemetry page. OIDC sign-in untested against a real IdP; brand approval pending. No scenario, pricing or FinOps screens; no setup wizard. | Real-IdP test; setup API and wizard; accessibility review. |
| Usage ledger and reconciliation | Implemented with account scoping (ADR 0008, proposed), SKU and source dimensions (ADR 0009, proposed). Only the Bedrock metric normalizer exists for cloud telemetry (no live calls); Foundry and Vertex not started. | Live collection with customer-granted access; confirm ADRs 0008 and 0009. |
| Export sanitizer and samples | Built and tested on invented values; reduces but does not prove anonymity | Owner review of sanitized output before any real file is shared. |
| Marketplace distribution | Gap analysis only; price and margin work is modelling only | See [marketplace](marketplace.md). |
| Guided setup | Proposed | Interactive flow and real verification tests. |
| Full portability | Proposed | Archive decision and validated fresh restore. |
| Operations and recovery | Proposed | Executable runbooks and tested recovery targets. |
| Licensing and support policy | Undecided (R-14) | Owner decision before any distribution. |

The strongest open gap is real-world verification: every connector, the importer, the migrations and sign-in are untested outside synthetic data. See the [risk register](risk-register.md) (R-26, R-27, R-29, R-30).

## Redesign proposal (2026-11-07)

The owner's brief reframes the product as an application-centric AI economics platform. The assessment, target architecture and four-phase roadmap are in [docs/economics](economics/README.md), with [ADR 0011](adr/0011-ai-economics-platform.md) proposed. ADR 0011 is now accepted and Phase 1 is largely built (see Current status). The milestones below are the original token-application plan and predate the redesign; they are kept for traceability and need reconciling with the [economics roadmap](economics/07-roadmap.md).

## Milestone 0: resolve prerequisites

Choose initial hosting/runtime, persistence, observation mode, Assessment transport, credential migration policy, licensing, and customer scope model. Convert open decisions into reviewed ADRs. Confirm whether initial cost scope includes billing ingestion, estimates, or tokens only.

## Milestone 1: application skeleton

Create the selected runtime/frontend/backend structure, reproducible local development, configuration validation, health endpoint, persistence migrations, tests, and CI. Implement customer OIDC and resource authorization before exposing provider data. No fake working install commands or empty success checks.

## Milestone 2: first vertical slice

Choose one provider for incremental delivery, implement its adapter and usage ledger, verify setup, and display provenance/freshness/coverage. Test secret custody, pagination, retries, deduplication, and role denial. Selecting one first does not remove Foundry/Bedrock/Vertex from required baseline scope.

## Milestone 3: full baseline

Add the remaining provider adapters; test provider-specific normalization and reconciliation. Implement and verify Assessment, guided onboarding, customer data controls, full export/import, and permission-safe restoration.

## Milestone 4: deployment readiness

Publish a supported customer-run install/upgrade/recovery package, verify artifact provenance, complete threat review and usability tests, exercise failure runbooks, and document supported versions/limits. Promote to pilot only with actual acceptance evidence.

## Scope discipline

Do not add iOS form workflows, appointments, vendor data custody, imposed retention periods, commercial operations, or assumed multi-cloud hosting. Forecasting/anomaly detection/PR cost projection and advanced billing features need separately approved scope.

Track risks in [risk register](risk-register.md). Work should remain reviewable; do not implement every proposed component as a separate service by default.
