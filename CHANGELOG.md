# Changelog

Record notable changes under Unreleased in the same PR. No product release or runtime support is established by this file. Versioning policy must be confirmed before the first software release.

## [Unreleased]

### Added

- Customer-hosted product requirements with stable REQ IDs and an indexed documentation set.
- Architecture, customer roles/identity, scoped Assessment, provider integration, and token-accounting contracts.
- Deployment/onboarding, full portability, customer-owned lifecycle, operations, and acceptance-test documentation.
- Delivery roadmap, design risk register, and three accepted product-boundary ADRs.
- Root agent instructions for implementation and review.

- API skeleton in `apps/api` (FastAPI health endpoints, configuration validation, deny-by-default role matrix, unit tests), skeleton Dockerfile, development-only compose file, and `.env.sample`.
- OIDC bearer-token verification (signature, issuer, audience, expiry, asymmetric algorithms only), IdP-group-to-role mapping, and a customer-set bootstrap admin identity; production config now requires an admin path. Dependencies PyJWT 2.15.1 and cryptography 50.0.2 pinned and checked with pip-audit.
- PostgreSQL layer (ADR 0006): role-assignment and audit tables, Alembic migration `0001` (`python -m cfa_tokenomics.migrate`), `PUT/DELETE /v1/admin/roles` with audit events and last-admin protection, database-aware `/readyz`. Effective role is the highest of bootstrap, IdP group and stored assignment. Tests run against real PostgreSQL when `CFA_TEST_DATABASE_URL` is set. SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.8 pinned and checked with pip-audit.
- Usage ledger (ADR 0007): request and aggregate observation tables with checkpoints (migration `0002`), idempotent request writes, revision-tracked aggregate windows, reconciliation rules that never add sources, adapter contract, and a Bedrock CloudWatch metric normalizer. Tests use labeled synthetic data only; no provider has been called.
- `GET /v1/usage` returns reconciled usage for a required, bounded time range (reconciliation status, app-observed, provider-reported, unattributed, partial flag, aggregate quality and revision, collection freshness). `GET /v1/whoami` is a database-free authentication check. Account scoping (ADR 0008, proposed): admins see all accounts; users and readers see only (provider, account) pairs granted to their identity via `PUT/DELETE /v1/admin/grants` (audited, migration `0003`). No grant means no data. Workspaces and group-based scoping are not implemented.
- UI concept drawings (token telemetry view and setup wizard) with brand tokens, static HTML and rendered images under `design/concepts/`, and `docs/ui-concepts.md`. Concepts only; brand approval pending.
- SKU and source dimensions (ADR 0009, proposed): `sku` (`api_on_demand`, `api_provisioned`, `subscription`, `unknown`) and `source_type` (`cloud_telemetry`, `vendor_admin_api`, `app_routed`) on all observations (migration `0004`; existing rows become `unknown`), `sku`/`source_type` filters on `GET /v1/usage`, and `GET /v1/usage/series` (one category per query, hour or day buckets, grouped by vendor/SKU/model/account, sources never added, windows longer than the bucket excluded and counted). No vendor admin API adapter yet.
- Web app in `apps/web` (React, TypeScript, Vite; exact-pinned dependencies, `npm audit` clean): token telemetry page with category counters, hourly series by vendor and SKU, source selector, weekday-by-hour heatmap, sources and freshness, and a reconciliation breakdown. Never adds sources; unknown shows "not reported"; accessible labels on charts and tables. OIDC sign-in (authorization code + PKCE, session storage) is written but untested against a real identity provider. A dev-only mock (`?mock=1`) is excluded from production builds.
- API serves the built web app same-origin (`CFA_WEB_DIR`), a public `GET /config.json`, `CFA_OIDC_CLIENT_ID`, and security headers (CSP, nosniff, no-referrer). The container image is now multi-stage and builds from the repository root; CI runs the web checks as an image build stage. Dependabot npm, pip and Docker blocks now point at `apps/web` and `apps/api`.
- ADR 0010 (accepted scope): vendor APIs for Claude Code, OpenAI Codex, Perplexity, Google Gemini and GitHub Copilot; cloud APIs for Bedrock, Foundry and Vertex AI; Microsoft Copilot via Graph and Viva. Nothing implemented or verified. Risks R-16 to R-18 added.
- AI economics redesign proposal in `docs/economics/` (current-state assessment and gap analysis with KEEP, REFACTOR, REMOVE, BUILD; target architecture; canonical data model aligned to FOCUS 1.4; connector framework with a documentation-sourced capability matrix; calculation engine; UX; four-phase roadmap), ADR 0011 (proposed), proposed requirements REQ-013 to REQ-022, and risks R-19 to R-23. No code changed.
- Phase 1 slice 1 (ADR 0011 accepted): economics calculation library in `apps/api/src/cfa_tokenomics/econ`. Exact-decimal arithmetic (floats refused), basis (observed, estimated, assumed) propagated through every result, unknown inputs give unknown results, mixed currencies refused, content-hashed nodes recording formula, inputs and basis for the explain view. Implements AI cost estimate, total and run cost, unit economics, business value (capacity and cashable), ROI, payback on run cost, price models (linear, usage, tiered), marketplace fee, required price, margin, break-even, commitments, driver-based scenario evaluation, and tornado and grid sensitivity. 37 tests reproduce the design's worked example exactly. Not yet connected to data or the API. `AGENTS.md` updated for the new scope.
- Phase 1 slice 2: economics core schema (migration `0005`): tenants, business units, customers, environments, applications, workloads, application customers, price books and entries, value assumptions, scenarios and drivers, calculation nodes and edges. Row-level security is forced on every table, keyed to a transaction-local tenant setting, and fails closed when none is set. Foreign keys include the tenant so cross-tenant references are impossible even for a privileged writer. Assumption history and calculation nodes are append-only (insert and select policies and grants only). Money is exact `NUMERIC`. Repository functions for tenants, applications, versioned assumptions (a rationale is required), non-overlapping price entries, scenarios, and saving or loading calculation trees with content-hash tamper detection. `/readyz` now refuses a database role that can bypass row-level security (`CFA_ALLOW_RLS_BYPASS` for dev only). `python -m cfa_tokenomics.admin` creates tenants and prints the runtime role grants. Existing usage, role and audit tables are not yet tenant-isolated.
- Node ids now hash the exact digits, basis mix, label and note (not the ambient decimal context), so a stored figure whose basis or wording was changed is detected.
- `api-ci.yml` workflow (lint, tests, image build; Actions pinned by SHA).
- Accepted ADRs 0004 (stack), 0005 (container packaging and marketplace), 0006 (persistence) and a [marketplace gap analysis](docs/marketplace.md).

### Changed

- Replaced the template README with Work-CFA_Tokenomics product scope, status, navigation, and non-goals.
- Customized contribution, security, Copilot, ownership, PR, and issue-routing guidance.
- Replaced template setup instructions with a maintainer checklist and explicit initialization-script warning.
- Distinguished requirements/proposals from implemented or verified functionality.

### Security

- Documented no-standing-vendor-access, customer credential custody, safe import authority handling, and customer-owned data policy as required boundaries, not implemented controls.
- Removed placeholder supported-version/contact promises; private reporting/settings remain to be verified.

### Not implemented

- Verification against a real identity provider, usage ledger, web UI, provider connectors, CI for the app, install templates, and marketplace listings. Previously listed as missing and still missing apart from the API skeleton: application runtime, deployable packages, provider connectors, data migrations, UI, and product tests. Existing security workflows and generic authoring templates remain in place.
