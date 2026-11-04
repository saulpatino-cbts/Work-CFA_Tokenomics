---
title: '[Workflow name]'
tool_type: '[Automation / Security / CI/CD / Utility]'
status: '[Draft / Active / Beta / Deprecated]'
maintainer: '[GitHub user or team]'
workflow_file: '.github/workflows/[filename].yml'
last_updated: 'YYYY-MM-DD'
---

# [Repository or project] — [Workflow name]

> **Purpose:** [One-sentence description of the problem this workflow solves.]

## Overview

[Explain what the workflow does, what it intentionally does not do, and where it fits in delivery or operations.]

| Attribute | Details |
| --- | --- |
| Type | [Automation / Security / CI/CD / Utility] |
| Trigger | [push / pull_request / schedule / workflow_dispatch / other] |
| Branches or paths | [Scope of automatic execution] |
| Runner | [Runner label or environment] |
| Timeout | [Configured timeout] |
| Permissions | [Minimum required token permissions] |

## Triggers and manual execution

Describe when the workflow runs, what filters apply, and whether it can be started manually.

    # Replace placeholders and use only with appropriate repository access.
    gh workflow run [filename].yml --field [input_name]=[value]

Or use GitHub: Actions -> [Workflow name] -> Run workflow.

## Flow

[Add a diagram when it clarifies sequence or decision points.]

    flowchart TD
        Start([Start]) --> Check[Validate inputs and context]
        Check -->|Valid| Action[Run controlled action]
        Check -->|Invalid| Fail[Stop with safe error]
        Action --> Result[Publish results]

## Configuration

### Inputs

| Name | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| [input_name] | [Yes/No] | [string/boolean/etc.] | [value] | [Purpose and allowed values] |

### Secrets and variables

- [SECRET_OR_VARIABLE] — [Purpose, owner, and least-privilege requirement]

Never document secret values. Explain where they are configured, how they are rotated, and which steps can read them.

## Outputs and side effects

- Artifact: [Name or none] — [Contents, retention, and access restrictions]
- Logs and summary: [Where results are found; confirm sensitive data is excluded]
- External side effects: [Resources, deployments, comments, or notifications changed]

## Expected behavior

When successful, the workflow should:

1. [Expected behavior]
2. [Expected behavior]
3. [Expected result or evidence]

Typical duration: [Approximate duration or variable].

## Security and reliability notes

- [ ] Permissions follow least privilege.
- [ ] Untrusted input is validated before use in commands, paths, expressions, or deployment parameters.
- [ ] Actions and dependencies are pinned or controlled according to repository policy.
- [ ] Secrets are not printed, uploaded, or included in artifacts.
- [ ] Production or destructive operations require approved environment protections.
- [ ] Retry, timeout, concurrency, cancellation, and rollback behavior is documented.
- [ ] Logs and summaries contain correlation identifiers, not credentials or sensitive content.

## Verification

- Static validation:
- Test or dry-run evidence:
- Permission and denial-path evidence:
- Deployment or runtime evidence, if applicable:
- Checks not run and why:

## Troubleshooting

| Error or symptom | Likely cause | Safe next step |
| --- | --- | --- |
| [Error message] | [Cause] | [Diagnostic or fix] |
| [Error message] | [Cause] | [Diagnostic or fix] |

## Rollback and recovery

[Describe how to stop, revert, disable, or recover from a failed or unsafe run. Include state migration and data recovery steps when applicable.]

## Related tools and documentation

- [Related workflow or tool](./related-tool.md) — [Relationship]
- [Repository documentation](../README.md) — [Relevant context]
- [Decision record or runbook](https://example.com) — [Why it matters]
