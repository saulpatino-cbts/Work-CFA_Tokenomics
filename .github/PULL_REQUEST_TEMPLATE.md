## Summary

<!-- Describe the outcome and distinguish documented/proposed/implemented/verified behavior. -->

## Related requirement or decision

<!-- Link REQ IDs, issue, risk, or ADR. Use a closing keyword only for work actually completed. -->

## Type of change

- [ ] Documentation or process
- [ ] Application or API
- [ ] Provider connector or accounting
- [ ] Identity, roles, or Assessment
- [ ] Data, import/export, or migration
- [ ] Infrastructure, CI, dependencies, or release
- [ ] Breaking change

## Scope and impact

<!-- Address APIs, data, permissions, resource isolation, compatibility, operations, and cost. State None when not applicable. -->

## Verification

- Exact commands/checks run:
- Results and what they prove:
- Checks not run and why:
- Evidence level: [ ] Static [ ] Local [ ] CI [ ] Authorized integration [ ] Production

## Product boundary review

- [ ] Customer data and credentials remain customer-controlled; no mandatory vendor data/control plane added.
- [ ] Admin/user/reader and resource denial paths covered where applicable.
- [ ] Vendor has no standing data access; Assessment approval/scope/revocation preserved.
- [ ] Usage semantics, provenance, unknown values, and deduplication preserved where applicable.
- [ ] Import/export validates data and authority; historical access is not reactivated.
- [ ] Customer owns data lifecycle; no commercial workflows or vendor retention policy added.
- [ ] No real secrets, customer content/exports, private identifiers, or sensitive telemetry included.

## Infrastructure and dependency review

<!-- Mark not applicable if untouched. -->

- [ ] Plan/preview and expected resource/cost changes reviewed.
- [ ] State, credentials, migrations, rollback/recovery, and compatibility documented.
- [ ] No unexpected destructive operations or unsafe resource renames.
- [ ] Dependencies/images/Actions justified and pinned; workflow permissions minimal.
- [ ] No cloud deployment or repository-setting change without explicit authorization.

## Documentation and delivery

- [ ] README/index and affected contracts updated.
- [ ] ADR/risk/roadmap/changelog updated where relevant.
- [ ] Remaining work and limitations named; no unrun checks presented as passed.
- [ ] Required review/CI status reported accurately; merge authorization not assumed.
