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

- Verification against a real identity provider, database layer, web UI, provider connectors, CI for the app, install templates, and marketplace listings. Previously listed as missing and still missing apart from the API skeleton: application runtime, deployable packages, provider connectors, data migrations, UI, and product tests. Existing security workflows and generic authoring templates remain in place.
