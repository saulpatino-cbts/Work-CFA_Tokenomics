# Repository instructions for GitHub Copilot

These apply to Copilot code review, Copilot coding agent and Copilot Chat in
this repository. `CONTRIBUTING.md` is the contract; this file points at it.

## When reviewing a pull request

- Put correctness, security and data handling first. Skip style that a
  formatter or linter already enforces.
- Name the input or state that triggers a defect, the wrong result, and the
  fix. A finding without a failure path is a suggestion, not a blocker.
- Check the description against `.github/PULL_REQUEST_TEMPLATE.md`: every
  section present, verification stated as commands and results, checks not
  run named.
- Flag any credential, token, connection string, personal data or private
  endpoint in code, tests, fixtures, examples, workflow files or comments.
- Flag a GitHub Action referenced by tag or branch instead of a commit SHA,
  and a workflow whose `permissions` are wider than its steps need.
- For Terraform, Bicep or other infrastructure, ask for the plan or preview
  and for the rollback step when the diff does not state them.

## When writing code

- Follow the existing structure, naming and tooling of the directory you
  are in; do not introduce a second formatter, test runner or lint config.
- Do not add a dependency, base image or Action without stating why and
  pinning it.
- Keep secrets out of source; read them from the environment or the
  platform's secret store.
- Add or update tests with the change, including the failure path.
- Do not merge, approve, publish, deploy or rewrite history.
