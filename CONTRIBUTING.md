# Contributing to Work-CFA_Tokenomics

Read [requirements](docs/requirements.md), [accepted ADRs](docs/adr/README.md), and [AGENTS.md](AGENTS.md) before substantial work. This is a documentation-stage customer-hosted platform, not an implemented SaaS. No license is selected; confirm contribution/distribution expectations with the owner.

## Workflow

1. Reference a requirement, issue, risk, or proposed ADR with observable acceptance criteria.
2. Create a focused branch from the current default branch.
3. Make the smallest coherent change; keep design proposals distinct from implementation claims.
4. Add tests with behavior changes, including authorization, failure, replay, and recovery cases.
5. Run applicable checks and inspect the final diff for secrets and unrelated changes.
6. Open a PR using the repository template; do not bypass required approvals or merge without authorization.

## Product invariants

Keep runtime data/credentials customer-controlled. Vendor identities have no standing customer access. Assessment cannot self-approve or silently expand scope. Customer admin/user/reader roles require backend enforcement. Preserve provider-specific token semantics and validated portability. Customer owns deletion/retention policy. Do not reintroduce commercial operations or earlier form-service assumptions.

Never commit real credentials, private keys, connection strings, customer archives, account identifiers, private endpoints, prompts/completions, or sensitive screenshots. Test fixtures must be sanitized/test-only and must not be represented as observed usage. Keep normal telemetry content-free and customer-local.

## Testing evidence

State exact commands, results, evidence level, and checks not run with reasons. Local documentation lint is not product validation or CI success. Mocked provider tests are not live integration evidence. See [test strategy](docs/testing.md).

## Architecture and infrastructure

Do not select a runtime, hosting platform, archive format, or Assessment transport implicitly. Use an ADR for trust-boundary or compatibility changes. Infrastructure work needs a reviewed plan, expected resource changes/costs, state/secret handling, rollout, migration, and recovery implications. Never commit state, saved plans, real variable files, or cloud credentials.

Pin/review dependencies, base images, and Actions consistently with existing policy. Do not add a tool, external service, workflow permission, or vendor endpoint without explaining need and data flow. Retain existing governance/security tooling unless a focused change deliberately replaces it.

## Documentation

Update README/index, affected contracts, tests, ADRs, risk register, and changelog with behavior changes. Source-controlled docs are canonical. Keep requirement IDs stable. No executable install/run command until it exists and is verified.

Do not run inherited initialization scripts in this customized repo; see [maintainer setup](docs/TEMPLATE.md). Report vulnerabilities according to [security policy](.github/SECURITY.md), not public issues with exploit details.
