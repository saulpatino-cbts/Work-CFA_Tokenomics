# Agent instructions

Applies to all repository content unless a more specific file intentionally narrows instructions without weakening security boundaries.

## Required context

Read `README.md`, `CONTRIBUTING.md`, `docs/requirements.md`, and accepted ADRs before implementation. Consult `docs/roadmap.md` and `docs/risk-register.md` for unresolved choices. This repository is at documentation/architecture foundation stage; do not claim a running product.

## Hard boundaries

- Customer-hosted runtime; no mandatory vendor data/control plane.
- Customer controls credentials, data, retention, deletion, backups, and upgrades.
- Customer admin/user/reader roles; vendor admin/support has no default customer-data access.
- Assessment requires customer approval, narrow scope, named identity, expiry/revocation, and local audit.
- Required integrations: Foundry, Bedrock, Vertex AI. Do not assume supporting their APIs means hosting on all three clouds.
- Preserve usage provenance and provider-specific semantics; unknown is not zero and overlap is not additive.
- Full export/import must validate data and authority; do not restore active sessions or support grants.
- No commercial operations, vendor-owned retention timer, iOS form processing, or appointment service.

## Working rules

Do not invent stack decisions, install commands, credentials, pricing, support SLAs, issue numbers, or test results. Document proposals explicitly. Add actual tests with code. Never send customer data/secrets to tools, reviews, telemetry, fixtures, or CI.

Preserve existing review/security configurations unless a scoped change explains replacement. Do not run inherited initialization scripts; they may overwrite project docs. Use repository templates and focused branches. Do not merge, publish, deploy, modify live cloud resources, or change repository settings without explicit authorization.

Report exact checks run and failures. Documentation lint is not runtime security evidence. A checklist is not a passed test. Update affected documentation and changelog with changes.
