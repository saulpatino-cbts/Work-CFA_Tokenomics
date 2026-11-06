# 0004. Application stack

- **Status:** Proposed
- **Date:** 2026-11-06
- **Decision authority:** Product owner (approval pending)
- **Owners:** Architecture
- **Requirements:** REQ-001, REQ-003, REQ-006, REQ-007, REQ-009
- **Issue:** No issue exists
- **Implementation evidence:** Pending; `apps/api` is a skeleton (health, config validation, deny-by-default authorization matrix, 20 unit tests). No web UI is scaffolded.

## Context

The product is downloaded from a cloud marketplace and run by the customer in the customer's account. The runtime must be small to ship, easy to scan and sign, and good at cloud-SDK and usage-data work. Resolves part of R-01.

## Decision

Propose: **Python 3.13 with FastAPI** for the API and workers (one image, multiple entrypoints), **React + TypeScript** for the web UI served as static assets, and **PostgreSQL** (ADR 0006). Dependencies are pinned. Provider SDKs (Azure, AWS, Google) all have first-class Python support, which suits the three required connectors.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| TypeScript end to end | One language | Weaker data-processing ecosystem for ledger/reconciliation | Python preferred for connectors and normalization |
| Go API + React | Small static binary | Slower iteration on data-heavy logic; fewer FinOps libraries | Proposed only if image size becomes a marketplace constraint |

## Consequences

Customer hosting and credential custody are unaffected by language choice. Supply chain: Python and npm dependencies need pinning, CVE review, and an SBOM before marketplace submission. Accessibility testing applies to the web UI once it exists.

## Validation

`ruff`, `pytest`, and container build in CI (CI not yet added). Negative authorization tests per role (started in `apps/api/tests/test_authz.py`). Untested: real OIDC verification, database access, provider adapters.

## Rollback or revisit trigger

Supersede this record if a marketplace image-size/scan requirement or provider SDK gap makes Python unsuitable.
