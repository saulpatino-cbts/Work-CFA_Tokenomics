# {{REPO_NAME}}

<!-- One paragraph: what this repository is for and who uses it. -->

## Getting started

<!-- Prerequisites, install, run, test. Keep commands one line, no placeholders. -->

## Repository standards

This repository was created from the organisation's template repository. It carries:

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
  `.github/SECURITY.md`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/` (bug, feature, ADR, FinOps finding,
  infrastructure change), `.github/labels.json`, `.github/release.yml`, and
  `.github/templates/` (blog, gist, task and workflow-document writing
  templates; not loaded by GitHub)
- `.github/workflows/codeql.yml` with `.github/codeql/codeql-config.yml`,
  `.github/workflows/dependency-review.yml`, `.github/dependabot.yml`
- `.github/copilot-instructions.md`, `.coderabbit.yaml` (CodeRabbit),
  `.qlty/qlty.toml` (Qlty), `.yamllint.yaml`, `.markdownlint.yaml`
- `.editorconfig`, `.gitattributes`, `.gitignore`, `docs/adr/`

Setup that no file can carry is listed in `docs/TEMPLATE.md`; delete that file
once the checklist there is done.
