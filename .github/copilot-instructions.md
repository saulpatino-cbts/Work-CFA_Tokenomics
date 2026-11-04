# Repository instructions for GitHub Copilot

Follow [AGENTS.md](../AGENTS.md) and [CONTRIBUTING.md](../CONTRIBUTING.md). Read [requirements](../docs/requirements.md), [ADRs](../docs/adr/README.md), and the affected product contracts before writing or reviewing changes.

## Writing changes

This is a customer-hosted platform at documentation-foundation stage. Do not invent a working runtime or choose unresolved architecture silently. Keep customer credentials/data local, preserve customer-owned lifecycle policy, enforce roles, and give vendor support no access outside an explicit Assessment grant.

Provider usage requires source-specific normalization, deduplication, and visible coverage. Import/export must validate integrity and authority and must not reactivate historical access. No commercial workflows or vendor retention timer.

Use existing tooling conventions; justify and pin dependencies/actions/images. Add failure and denial tests with code. Never add real secrets, customer content, archives, private endpoints, or identifiable telemetry. Do not run inherited template initialization scripts. Do not merge, deploy, publish, change repository settings, or rewrite history.

## Reviewing changes

Prioritize correctness, authorization, credential custody, usage accuracy, and migration safety. Describe the triggering input/state, wrong outcome, and fix; distinguish a concrete defect from an optional design suggestion.

Check requirement/ADR links, tests, unrun checks, and claimed status. Flag broadened support scope, secret exposure, missing authorization, overlapping usage totals, blind imports, false verification UI, and vendor-controlled data policy. Infrastructure changes need plan/state/recovery evidence. Workflow permissions must be minimal and Actions pinned consistently with repository policy.
