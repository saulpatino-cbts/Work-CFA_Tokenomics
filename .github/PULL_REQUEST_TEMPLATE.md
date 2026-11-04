## Summary

<!-- What changed, why, and who or what is affected? Link the related issue,
decision record, task, finding, or review item when one exists. -->

## Related issue or decision

<!-- Use a closing keyword only when this pull request completes the issue. -->

Closes #

## Type of change

- [ ] Feature or behavior change
- [ ] Bug fix
- [ ] Refactor or performance improvement
- [ ] Documentation or process change
- [ ] Dependency update
- [ ] CI/CD or repository policy change
- [ ] Infrastructure or deployment change
- [ ] Security or privacy change
- [ ] Breaking change

## Scope and impact

<!-- Describe affected components, APIs, data, permissions, tenancy, migrations,
operations, rollout, compatibility, and rollback considerations. Say "None"
where a category does not apply. -->

## Verification

<!-- List exact commands or checks and what each result proves. State checks not
run and why. Distinguish static, local, CI, staging, and production evidence. -->

- Checks run:
- Important result or evidence:
- Checks not run and why:
- Evidence level: [ ] Static [ ] Local [ ] CI [ ] Staging [ ] Production

## Infrastructure changes only

<!-- Remove this section when infrastructure is untouched. -->

- [ ] Plan or preview was reviewed; no unexpected destroy/recreate operations exist.
- [ ] Resource addresses were not renamed without the required moved-state handling.
- [ ] Secrets, state files, saved plans, and real variable values are not included.
- [ ] Required tags, policies, networking, backup, identity, and security settings are preserved.
- [ ] Rollout, monitoring, rollback, and recovery steps are documented.

## Security and data review

- [ ] No credentials, private keys, tokens, connection strings, personal data, customer data, or sensitive content was added.
- [ ] Telemetry is content-free and uses correlation identifiers rather than paths, query strings, route values, document identifiers, or payloads.
- [ ] Authorization, tenant isolation, least privilege, and denial paths were tested where applicable.
- [ ] New dependencies, base images, and GitHub Actions are pinned or controlled according to repository policy.
- [ ] No automated path can activate, approve, sign, file, or make an authoritative write unless explicitly approved.

## Documentation and operations

- [ ] User-facing or developer documentation updated when needed.
- [ ] Release notes, changelog, runbook, architecture record, migration notes, or security records updated when needed.
- [ ] Remaining work is recorded in the repository's established tracker.
- [ ] Rollout and rollback owners are identified when the change affects a shared environment.

## Author checklist

- [ ] The pull request is focused and unrelated edits were removed.
- [ ] Tests cover changed behavior and important failure, boundary, and denial paths.
- [ ] The final diff contains no local configuration, generated artifacts, or secrets that do not belong.
- [ ] Required reviewers, approvals, environments, and CI checks are complete or explicitly called out.
