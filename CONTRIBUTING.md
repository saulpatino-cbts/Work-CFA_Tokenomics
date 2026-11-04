# Contributing

Thank you for contributing. These guidelines are the default contract for this repository. More specific instructions in a root or nested CONTRIBUTING.md, AGENTS.md, README, or project document take precedence for the files they cover.

## Before you start

- Search existing issues and pull requests before opening a new one.
- For substantial work, open or reference an issue with a clear outcome and acceptance criteria.
- Do not include credentials, tokens, private keys, connection strings, personal data, customer data, or sensitive infrastructure details in source, tests, fixtures, examples, logs, issues, or pull requests.
- Report suspected vulnerabilities privately using `.github/SECURITY.md`.
- Confirm the repository license, `CODE_OF_CONDUCT.md`, and any contributor-license or disclosure requirements before contributing.

## Development workflow

1. Create a focused branch from the current default branch.
2. Make the smallest coherent change that solves the stated problem.
3. Preserve existing behavior unless a behavior change is intentional and documented.
4. Add or update tests, including failure, boundary, authorization, and tenant-isolation cases when applicable.
5. Run the checks documented by the repository and its CI workflows.
6. Inspect the final diff for secrets, local configuration, generated output, accidental files, and unrelated changes.
7. Open a pull request using the canonical template.

Do not push directly to a protected default branch or bypass required reviews, checks, environments, or CODEOWNERS approvals.

## Testing evidence

State:

- exact commands or checks run;
- the important result and what it proves;
- checks not run and why;
- whether evidence is static, local, CI, staging, or production; and
- any remaining uncertainty or follow-up.

Tests should fail when the intended behavior is broken. Where practical, mutate the relevant implementation or assertion temporarily and confirm the test catches the change; this helps detect vacuous tests.

## Pull requests

- Keep each pull request focused and reviewable.
- Link the issue, decision record, task, or finding when one exists.
- Describe user-visible, API, data, security, operational, infrastructure, migration, rollout, compatibility, and rollback effects.
- Call out new permissions, dependencies, actions, base images, trust-boundary changes, and breaking changes.
- Include screenshots, logs, plans, or API output only when sanitized and useful.
- Do not merge while required checks, approvals, or security review are missing.

## Infrastructure and IaC

Infrastructure changes must include a reviewed plan or preview, expected create/update/destroy behavior, state or migration considerations, cost impact, required inputs, rollback or recovery steps, and relevant security or policy effects. Do not commit state files, saved plans, real variable values, or credentials.

For Terraform modules, follow the repository's chosen provider and module standards. If Azure Verified Modules compatibility is a goal, validate provider constraints, variable and output contracts, provider declaration rules, module source/version pinning, documentation generation, formatting, static analysis, and tests against the current AVM requirements rather than relying only on this document.

## Security and data invariants

Unless the repository documents an approved exception:

- keep credentials and sensitive data out of source control, build artifacts, logs, fixtures, examples, and comments;
- keep telemetry content-free and use correlation identifiers rather than paths, query strings, route values, document identifiers, or payloads;
- test authorization, least privilege, tenant isolation, and denial paths where applicable;
- keep automated components from activating, approving, signing, filing, or making authoritative writes unless explicitly approved; and
- control dependencies, base images, and GitHub Actions through pinning, review, and Dependabot or an equivalent process.

## Documentation and follow-up

Update user, developer, operational, security, architecture, decision, release, and migration documentation when behavior or assumptions change. Record unrelated findings in the established tracker rather than expanding the current pull request.
