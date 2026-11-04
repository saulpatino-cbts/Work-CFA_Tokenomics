---
name: Infrastructure change request
about: Propose a planned change to infrastructure, deployment, identity, networking, data, or platform configuration
title: "[Infrastructure]: "
labels: infrastructure
assignees: ""
---

<!-- Do not include credentials, tokens, private keys, connection strings, state files, or sensitive identifiers. -->

## Change and desired end state

<!-- What resource, configuration, or platform behavior changes? What should the final state be? -->

## Why

<!-- Business, reliability, security, cost, compliance, or engineering driver. If this alters an accepted ADR, identify it and create a new ADR before implementation. Use the Architecture decision record issue form and link the decision record when one exists. -->

## Scope and blast radius

- Components or resources touched:
- Environments affected:
- Stateful data or persistent resources affected, and their deletion protection:
- Expected replacement, migration, or downtime:
- Dependencies and consumers:
- Authorization or trust-boundary impact:

## Cost and operational impact

- Estimated recurring and one-time cost:
- Cost impact versus the repository's documented cost ceiling, if one exists:
- Performance, availability, backup, monitoring, or support impact:
- New required inputs, approvals, or secrets:
- New required inputs to record in the repository's review or operations documentation:

## Validation plan

<!-- Include the exact plan, preview, test, or dry-run evidence expected before apply. -->

- [ ] Configuration and policy validation completed.
- [ ] Plan or preview reviewed for unexpected changes.
- [ ] Security and least-privilege implications reviewed.
- [ ] Backup, migration, and data-protection implications reviewed.
- [ ] Rollout and monitoring plan documented.

## Rollback and recovery

<!-- Explain how to reverse or contain the change if it misbehaves. Include state migration and data recovery steps when applicable. -->

## Acceptance criteria

- [ ] Desired end state is documented and verified.
- [ ] Required reviewers and approvals are identified.
- [ ] No secrets, state files, saved plans, or real variable values are included.
- [ ] Documentation, runbooks, change records, or release notes are updated when needed.

## Evidence and follow-up

<!-- Link sanitized plan output, test results, dashboards, or decision records. Record remaining work separately. -->
