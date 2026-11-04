# From template to running repository

Created from the template repository. Work this list once, then delete this
file.

## 1. Initialize the checkout (one command)

```powershell
.\scripts\Initialize-Repo.ps1 -Stack node-typescript -Prune
```

Bash (Git Bash):

```bash
bash scripts/initialize-repo.sh --prune node-typescript
```

Owner and repository name are read from the `origin` remote; pass `-Name`
or `-Owner` only to override them. Parameters and expected output are
documented in the template repository's README and in the scripts' own help
(`Get-Help .\scripts\Initialize-Repo.ps1 -Detailed`,
`bash scripts/initialize-repo.sh --help`).

Stacks: `node-typescript`, `python`, `terraform-ansible`; pass several with
commas, or none for a docs-only repository. The script:

- replaces the template's `README.md` with the project README skeleton from
  `docs/README.project.md`, titled with the repository name;
- writes `* @<owner>` into `.github/CODEOWNERS`, the owner being the origin
  remote's account (pass `-Owner @org/team` for a team);
- removes `.github/dependabot.yml` blocks whose manifest does not exist, so
  Dependabot does not report missing manifests;
- appends the stack's plugins to `.qlty/qlty.toml`;
- points `.github/ISSUE_TEMPLATE/config.yml` at this repository's Discussions;
- adds the stack's CodeQL languages to `.github/workflows/codeql.yml`
  (`actions` is always analysed);
- with `gh` signed in, creates the labels in `.github/labels.json` (the issue
  forms, Dependabot and `release.yml` rely on them) and enables Discussions,
  which the issue chooser links to;
- deletes `overlays/` and the scripts themselves with `-Prune`.

Then review `.github/SECURITY.md`: its "Supported versions" and "Maintainer
contact" sections are placeholders by design and must be replaced by hand.

Then add a `LICENSE` if the repository is public: the template ships none
because the licence is a per-repository decision.

## 2. Connect the three apps (browser)

1. <https://github.com/settings/installations> : Configure CodeRabbit, Qlty and
   GitGuardian, and add this repository to each.
2. <https://qlty.sh/dashboard> : Add Project for this repository.
3. Open one pull request and look for three signals: `GitGuardian Security
   Checks`, the `qlty check` commit status, and a CodeRabbit walkthrough. A
   public repository under 10 stars gets a CodeRabbit review only when asked:
   comment `@coderabbitai review`.

GitGuardian's own settings live at
<https://dashboard.gitguardian.com/settings/integrations/github> and apply to the
whole account: check runs on, conclusion **Failed**, skip actions on, PR
comment on, **Skip merge commits in pull request check runs** on.

## 3. CodeQL: advanced setup, not default

`codeql.yml` is an advanced-setup workflow because only that honours
`.github/codeql/codeql-config.yml`. If the repository shows CodeQL default
setup as enabled, the workflow fails with "CodeQL analyses from advanced
configurations cannot be processed when the default setup is enabled". Turn
default setup off at
`https://github.com/{{REPO_SLUG}}/settings/security_analysis` under
**Code scanning > CodeQL analysis**, then re-run the workflow. Discussions
must be enabled on the same settings page's General tab for the
`config.yml` contact link to resolve; otherwise remove that link.

`dependency-review.yml` runs on public repositories; on a private one it
needs a GitHub Advanced Security licence, otherwise delete the workflow.

## 4. Ruleset (optional, after the first green PR)

Require the checks you saw in step 2.3 and the `Analyze (actions)` job. Do not make CodeRabbit's approval the
required review unless the app has **Pull requests: Read and write** and the
repository can live with one included review per hour on the open-source tier.

## How the configs are layered

- `.coderabbit.yaml` is complete and stack-agnostic: path instructions keyed by
  glob cost nothing where the glob matches no file, and tools that need a
  project config run only where one exists.
- `.qlty/qlty.toml` holds only plugins that need no project config; stack
  plugins come from `overlays/<stack>/qlty.toml.part`, because a Qlty plugin
  pointed at a missing config fails every run.
- `.github/dependabot.yml` ships every ecosystem; `Initialize-Repo.ps1` prunes
  it to the manifests present.
