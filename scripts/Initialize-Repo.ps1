<#
.SYNOPSIS
Turns a checkout created from the template into a ready repository.

.DESCRIPTION
Run once from the root of a repository created from the template, before
committing your own code. Replaces README.md with the project skeleton,
writes CODEOWNERS, prunes dependabot.yml to the manifests present, points
the issue chooser at the repository, adds the stack's CodeQL languages and
Qlty plugins, and with gh signed in creates labels and enables Discussions.
Safe to run again: every step checks whether it has already been done.

.PARAMETER Name
Repository name. Default: read from the origin remote.

.PARAMETER Owner
Code owner written to .github/CODEOWNERS, a user (@login) or a team
(@org/team). Default: the account in the origin remote.

.PARAMETER Stack
Technology in the repository: node-typescript, python, terraform-ansible.
Several allowed; none for a docs-only repository.

.PARAMETER Prune
Delete overlays/ and scripts/ when done.

.PARAMETER SkipGitHub
Do not call gh. Labels and Discussions must then be set up by hand.

.EXAMPLE
PS> .\scripts\Initialize-Repo.ps1 -Stack node-typescript -Prune

.EXAMPLE
PS> .\scripts\Initialize-Repo.ps1 -Owner @example-org/platform -Stack python,terraform-ansible
#>
[CmdletBinding()]
param(
  [string] $Name,
  [string] $Owner,
  [ValidateSet('node-typescript','python','terraform-ansible')] [string[]] $Stack = @(),
  [switch] $Prune,
  [switch] $SkipGitHub
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

$origin = (git config --get remote.origin.url 2>$null)
$slug = ''
if ($origin -match '[:/]([^/:]+)/([^/]+?)(\.git)?/?$') { $slug = "$($Matches[1])/$($Matches[2])" }
if (-not $Name)  { $Name  = if ($slug) { $slug.Split('/')[1] } else { Split-Path -Leaf $root } }
if (-not $Owner) { if ($slug) { $Owner = '@' + $slug.Split('/')[0] } else { throw 'No origin remote found: pass -Owner @login' } }
$login = ($Owner.TrimStart('@') -split '/')[0]
$slug = "$login/$Name"

# README: the template's README gives way to the project README
$skeleton = Join-Path $root 'docs\README.project.md'
if (Test-Path $skeleton) {
  (Get-Content $skeleton -Raw).Replace('{{REPO_NAME}}', $Name) | Set-Content (Join-Path $root 'README.md') -NoNewline
  Remove-Item $skeleton
  Write-Host "README.md: project README written for $Name"
}

# CODEOWNERS
$co = Join-Path $root '.github\CODEOWNERS'
$t = Get-Content $co -Raw
if ($t -notmatch "(?m)^\*\s+$([regex]::Escape($Owner))\s*$") { $t = $t.Replace('# * @ORG/REPOSITORY-MAINTAINERS', "* $Owner") }
Set-Content $co $t -NoNewline
Write-Host "CODEOWNERS: * $Owner"

# Dependabot: keep only ecosystems whose manifest exists
$db = Join-Path $root '.github\dependabot.yml'
$t = Get-Content $db -Raw
$marker = '# Optional additional directories'
$i = $t.IndexOf($marker); $body = $t.Substring(0, $i); $tail = $t.Substring($i)
$chunks = [regex]::Split($body, '(?m)(?=^  - package-ecosystem:)')
for ($i = 0; $i -lt $chunks.Length - 1; $i++) {  # a block's leading comment lines sit at the end of the previous chunk; move them
  $lines = $chunks[$i] -split "`n"
  $j = $lines.Length - 1; while ($j -gt 0 -and $lines[$j] -eq '') { $j-- }
  $k = $j; while ($k -ge 0 -and $lines[$k].StartsWith('  #')) { $k-- }
  if ($k -ge 0 -and $k -lt $j) {
    $chunks[$i + 1] = (($lines[($k + 1)..$j]) -join "`n") + "`n" + $chunks[$i + 1]
    $chunks[$i] = (($lines[0..$k]) -join "`n") + "`n"
  }
}
$head = $chunks[0]; $blocks = $chunks[1..($chunks.Length - 1)]
$present = @{
  'npm'            = (Test-Path (Join-Path $root 'package.json'))
  'pip'            = @('requirements.txt','pyproject.toml','poetry.lock','Pipfile') | Where-Object { Test-Path (Join-Path $root $_) } | Select-Object -First 1
  'github-actions' = $true
  'terraform'      = [bool](Get-ChildItem $root -Filter '*.tf' -File -ErrorAction SilentlyContinue)
  'docker'         = (Test-Path (Join-Path $root 'Dockerfile'))
}
$kept = @(); $dropped = @()
foreach ($b in $blocks) {
  if ($b -match 'package-ecosystem:\s*"([^"]+)"') { $eco = $Matches[1] } else { $kept += $b; continue }
  if ($present[$eco]) { $kept += $b } else { $dropped += $eco }
}
Set-Content $db (($head + ($kept -join '')).TrimEnd() + "`n`n" + $tail) -NoNewline
Write-Host ("dependabot.yml: kept " + (($present.Keys | Where-Object { $present[$_] }) -join ', ') + "; dropped " + ($(if ($dropped) { $dropped -join ', ' } else { 'nothing' })))

# Issue chooser links, docs slug, CodeQL languages
$cfg = Join-Path $root '.github\ISSUE_TEMPLATE\config.yml'
$t = (Get-Content $cfg -Raw).Replace('ORG/REPO', $slug).Replace("# Replace ORG/REPO before installing this file.`n", '')
Set-Content $cfg $t -NoNewline; Write-Host "ISSUE_TEMPLATE/config.yml: links point at $slug"
$doc = Join-Path $root 'docs\TEMPLATE.md'
(Get-Content $doc -Raw).Replace('{{REPO_SLUG}}', $slug) | Set-Content $doc -NoNewline
$langMap = @{ 'node-typescript' = 'javascript-typescript'; 'python' = 'python' }
$extra = @($Stack | Where-Object { $langMap.ContainsKey($_) } | ForEach-Object { $langMap[$_] })
if ($extra.Count -gt 0) {
  $wf = Join-Path $root '.github\workflows\codeql.yml'
  (Get-Content $wf -Raw).Replace('language: [actions]', 'language: [actions, ' + ($extra -join ', ') + ']') | Set-Content $wf -NoNewline
  Write-Host ("codeql.yml: languages actions, " + ($extra -join ', '))
}

# Qlty stack overlays
$qlty = Join-Path $root '.qlty\qlty.toml'
foreach ($s in $Stack) {
  $part = Join-Path $root "overlays\$s\qlty.toml.part"
  if (-not (Test-Path $part)) { continue }
  $first = (Select-String -Path $part -Pattern '^name = ' | Select-Object -First 1).Line
  if ((Get-Content $qlty -Raw).Contains($first)) { Write-Host "qlty.toml: $s already present" }
  else { Add-Content -Path $qlty -Value ("`n" + (Get-Content $part -Raw)); Write-Host "qlty.toml: appended $s" }
}

# Labels and Discussions through gh, when signed in
$ghOk = $false
if (-not $SkipGitHub -and (Get-Command gh -ErrorAction SilentlyContinue)) { gh auth status *> $null; $ghOk = ($LASTEXITCODE -eq 0) }
if ($ghOk) {
  foreach ($l in (Get-Content (Join-Path $root '.github\labels.json') -Raw | ConvertFrom-Json)) {
    gh label create $l.name --color $l.color --description $l.description --force --repo $slug *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "label: $($l.name)" }
  }
  gh repo edit $slug --enable-discussions *> $null
  if ($LASTEXITCODE -eq 0) { Write-Host "discussions: enabled on $slug" }
} elseif ($SkipGitHub) {
  Write-Host 'GitHub step skipped: labels and Discussions are listed in docs/TEMPLATE.md step 2.'
} else {
  Write-Host 'gh not available or not signed in: create the labels in .github/labels.json and enable Discussions by hand (docs/TEMPLATE.md step 2).'
}

if ($Prune) {
  Remove-Item -Recurse -Force (Join-Path $root 'overlays'), (Join-Path $root 'scripts')
  Write-Host 'pruned overlays/ and scripts/'
}
Write-Host ''
Write-Host 'Next: docs/TEMPLATE.md section 2 (connect the three apps), then replace the placeholder sections in .github/SECURITY.md.'
