# Delivery roadmap

## Current status

The repository began as a governance/security template. This documentation foundation defines the customer-hosted product; it does not implement application code, connectors, infrastructure, migrations, or runtime tests. No production release or deployment command exists.

| Area | Status | Next evidence |
| --- | --- | --- |
| Product boundaries and role names | Documented | Owner review of requirements and accepted ADRs. |
| Permission matrix and Assessment lifecycle | Proposed detailed contract | Scope approval, transport ADR, negative tests. |
| Runtime and hosting | Accepted (ADRs 0004-0006) | Install templates and a tested fresh install. |
| API skeleton | Started (`apps/api`) | Real-IdP test, usage ledger, first CI run on GitHub. |
| Marketplace distribution | Gap analysis only | See [marketplace](marketplace.md). |
| Provider adapters | Bedrock metric normalizer only (no live calls, no credentials, no scheduler); Foundry and Vertex not started | Live collection with customer-granted access; adapters for the other two. |
| Usage ledger/reconciliation | Started: tables, migration, reconciliation rules, tests (synthetic data) | Live-provider verification; UI. A read API exists (`GET /v1/usage`) with per-identity account scoping (ADR 0008, proposed). |
| Guided setup | Proposed | Interactive flow and real verification tests. |
| Full portability | Proposed | Archive decision and validated fresh restore. |
| Operations and recovery | Proposed | Executable runbooks and tested recovery targets. |

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
