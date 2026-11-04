# Maintainer repository setup

This repository has been customized for Work-CFA_Tokenomics. This file replaces the inherited template checklist; it is not a product deployment guide.

## Initialization warning

Do not rerun `scripts/Initialize-Repo.ps1` or `scripts/initialize-repo.sh` against this customized checkout. They are inherited template utilities and can overwrite README content, prune files, alter review tooling, and change GitHub settings. `overlays/` does not select the application stack. Remove/archive these utilities through a deliberate tooling change after deciding what the project needs.

## Settings requiring verification

- [ ] Confirm default branch, branch/ruleset protection, required reviews, and emergency recovery.
- [ ] Confirm CODEOWNERS resolves to the intended maintainer; file presence does not enforce approval.
- [ ] Enable and test a private vulnerability reporting channel before inviting security reports with sensitive details.
- [ ] Decide repository license and contribution/distribution policy; no license is currently selected.
- [ ] Verify labels referenced by issue forms, Dependabot, and release notes actually exist.
- [ ] Confirm CodeQL advanced setup is compatible with repository settings and entitlement.
- [ ] Confirm dependency review availability for repository visibility/licensing.
- [ ] Verify CodeRabbit, Qlty, GitGuardian, or other review integrations only if intentionally used.
- [ ] Require only checks actually observed and understood; do not claim green checks without run evidence.

These are unverified tasks, not claims that settings have been applied. Do not enable external apps or grant new repository permissions without owner approval.

## Documentation source of truth

Use [documentation index](README.md) and source-controlled ADRs. The issue chooser links to repository documentation, not an assumed enabled Discussions/wiki service. Reusable authoring templates remain under `.github/templates/`.

The legacy `docs/README.project.md` is kept only as input to inherited scripts and points back to the canonical README. It is not product setup documentation.

## When code is introduced

Select tooling through ADRs, add only applicable dependency manifests, configure Dependabot for real paths, extend CodeQL to implemented languages, and add documented test/lint commands. Inherited workflow checks are not a substitute for product tests.
