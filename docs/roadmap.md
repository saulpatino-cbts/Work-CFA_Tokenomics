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
| Licensing, support, retention | Decided in ADR 0014: proprietary, no support commitment, client-chosen retention. Legal text and the retention design are not done (R-14). | Legal review; owner decisions on [ADR 0015](adr/0015-retention-controls-and-time-zone-setting.md) (proposed design for retention and the time zone setting). |

The strongest open gap is real-world verification: every connector, the importer, the migrations and sign-in are untested outside synthetic data. See the [risk register](risk-register.md) (R-26, R-27, R-29, R-30).

## Redesign proposal (2026-11-07)

The owner's brief reframes the product as an application-centric AI economics platform. The assessment, target architecture and four-phase roadmap are in [docs/economics](economics/README.md), with [ADR 0011](adr/0011-ai-economics-platform.md) proposed. ADR 0011 is now accepted and Phase 1 is largely built (see Current status). The milestones below are the original token-application plan and predate the redesign; they are kept for traceability and need reconciling with the [economics roadmap](economics/07-roadmap.md).

## Milestones (reconciled 2026-11-12)

These replace the original token-application milestones. They follow the [economics roadmap](economics/07-roadmap.md) and ADR 0011. Order matters: real data before real connectors, sign-in testing near the end.

| Milestone | Scope | State |
| --- | --- | --- |
| 0. Prerequisites | Hosting, persistence, observation mode, scope (ADRs 0004 to 0007, 0010, 0011, 0013). One client per install, deployed from the Azure and AWS marketplaces or standalone (ADR 0011 assumption 1). | Largely decided. License (proprietary), support (none promised), retention (client's choice) and time zone (UTC, administrator-selectable) are recorded in ADR 0014, with legal text pending. Open: retention design, Assessment transport (R-02). |
| 1. Skeleton | API, web app, migrations, CI, authorization | Done on synthetic data. |
| 2. Economics foundation (Phase 1) | Calculation engine, data model, FOCUS import, allocation, economics API and screens, usage facts | Done on synthetic data. Acceptance needs a real FOCUS export (see [test readiness](economics/11-test-readiness.md)). |
| 3. Real telemetry (Phase 2) | Cost-export and vendor connectors, per-user mode, directory sync, scheduler | Cost-export, Anthropic and Codex connectors built against fakes. The rest is not built. Needs real accounts and a readiness decision per connector. |
| 4. Commercialization (Phase 3) | Price, margin and marketplace modelling (modelling only) and the remaining screens | Not started. |
| 5. Deployment readiness (Phase 4) | Marketplace packages for Azure and AWS, a standalone install, upgrade and recovery, full export/import, Assessment, a threat review. Real identity provider test (Entra ID first, Google Workspace second), deliberately late. | Not started. |

## Scope discipline

Do not add iOS form workflows, appointments, vendor data custody, imposed retention periods, commercial operations, or assumed multi-cloud hosting. Forecasting/anomaly detection/PR cost projection and advanced billing features need separately approved scope.

Track risks in [risk register](risk-register.md). Work should remain reviewable; do not implement every proposed component as a separate service by default.
