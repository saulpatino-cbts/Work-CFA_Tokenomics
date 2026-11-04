# Repository template

A GitHub template repository. Create a repository from it, run one command,
and the new repository has its governance files, review-app configuration,
security workflows and labels in place.

## Create a repository from it

1. On this repository's page choose **Use this template**, then **Create a
   new repository**. Name it and create it.
2. Clone the new repository and open a shell in its root folder.
3. Run the initialize script once (next section).
4. Work through `docs/TEMPLATE.md`, then delete that file.

## Initialize the checkout

PowerShell (Windows):

```powershell
.\scripts\Initialize-Repo.ps1 -Stack node-typescript -Prune
```

Bash (Git Bash, macOS, Linux; needs Python 3):

```bash
bash scripts/initialize-repo.sh --prune node-typescript
```

Both scripts do the same work. Run one of them, from the repository root,
before committing any code of your own. Running it a second time is safe:
every step checks whether it has already been done.

### Parameters

| PowerShell | Bash | Meaning |
| --- | --- | --- |
| `-Stack <list>` | words after the flags | Technology in the repository: `node-typescript`, `python`, `terraform-ansible`. Give several, or none for a docs-only repository. |
| `-Prune` | `--prune` | Delete `overlays/` and `scripts/` when done. Recommended. |
| `-Name <repo>` | `--name <repo>` | Repository name. Default: read from the `origin` remote. |
| `-Owner @login` | `--owner @login` | Code owner, a user or `@org/team`. Default: the account in the `origin` remote. |
| `-SkipGitHub` | `--skip-github` | Do not call `gh`. Labels and Discussions must then be set up by hand. |

Full help: `Get-Help .\scripts\Initialize-Repo.ps1 -Detailed` or
`bash scripts/initialize-repo.sh --help`.

### What it does

1. Replaces this README with the project README skeleton from
   `docs/README.project.md`, titled with the repository name.
2. Writes `* @<owner>` into `.github/CODEOWNERS`.
3. Removes every `.github/dependabot.yml` block whose manifest is absent
   (no `package.json`, no npm block), so Dependabot reports nothing missing.
4. Points the issue chooser (`.github/ISSUE_TEMPLATE/config.yml`) and
   `docs/TEMPLATE.md` at the new repository.
5. Adds the stack's CodeQL languages to `.github/workflows/codeql.yml`.
   Workflow files (`actions`) are always analysed.
6. Appends the stack's Qlty plugins from `overlays/<stack>/qlty.toml.part`
   to `.qlty/qlty.toml`.
7. With `gh` signed in: creates the labels in `.github/labels.json` and
   enables Discussions. Otherwise it says so and continues.
8. With `-Prune`: deletes `overlays/` and `scripts/`.

### What success looks like

```text
README.md: project README written for Demo_App
CODEOWNERS: * @example-org
dependabot.yml: kept npm, github-actions ; dropped pip, terraform, docker
ISSUE_TEMPLATE/config.yml: links point at example-org/Demo_App
codeql.yml: languages actions, javascript-typescript
qlty.toml: appended node-typescript
label: bug ... discussions: enabled on example-org/Demo_App
pruned overlays/ and scripts/
```

The script stops at the first error and prints it. Fix the cause and run it
again. Nothing it does needs input while it runs.

### Requirements

- Git, with the new repository's `origin` remote set (a normal clone has it).
- PowerShell 5.1 or 7 for the `.ps1`; Bash and Python 3 for the `.sh`.
- Optional: GitHub CLI signed in (`gh auth status`) for labels and Discussions.

## What the template contains

- Governance: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
  `.github/SECURITY.md`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`.
- Issues: `.github/ISSUE_TEMPLATE/` forms for bug, feature, ADR, FinOps
  finding and infrastructure change; `.github/labels.json`;
  `.github/release.yml` for generated release notes.
- Writing templates in `.github/templates/` (blog, gist, task, workflow
  document). GitHub does not load these; they are for copying.
- Security: `.github/workflows/codeql.yml` with
  `.github/codeql/codeql-config.yml`, `.github/workflows/dependency-review.yml`,
  `.github/dependabot.yml`.
- Review apps: `.coderabbit.yaml` (CodeRabbit), `.qlty/qlty.toml` plus
  `overlays/` (Qlty), `.github/copilot-instructions.md`; lint configuration
  `.yamllint.yaml` and `.markdownlint.yaml`.
- Hygiene: `.editorconfig`, `.gitattributes`, `.gitignore`; `docs/adr/`
  for decision records.
- `docs/TEMPLATE.md`: the post-creation checklist for the steps no file can
  carry (connecting the apps, repository settings).
