#!/usr/bin/env bash
# Turns a checkout created from the template into a ready repository.
# Usage: bash scripts/initialize-repo.sh [--name repo] [--owner @login|@org/team] [--prune] [--skip-github] [stack ...]
# Stacks: node-typescript python terraform-ansible. Owner and name default to the origin remote.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; cd "$root"
origin="$(git config --get remote.origin.url 2>/dev/null || true)"
slug="$(printf '%s' "$origin" | sed -E 's#\.git$##; s#/$##' | awk -F'[:/]' 'NF>=2{print $(NF-1)"/"$NF}')"
name="${slug##*/}"; [ -n "$name" ] || name="$(basename "$root")"
owner="@${slug%%/*}"; [ "$owner" != "@" ] || owner=""
prune=0; skip_github=0; stacks=()
while [ $# -gt 0 ]; do case "$1" in
  --name) name="$2"; shift 2;; --owner) owner="$2"; shift 2;;
  --prune) prune=1; shift;; --skip-github) skip_github=1; shift;;
  -h|--help) sed -n '2,4p' "$0"; exit 0;;
  *) stacks+=("$1"); shift;; esac; done
[ -n "$owner" ] || { echo "No origin remote found: pass --owner @login" >&2; exit 2; }
login="${owner#@}"; login="${login%%/*}"; slug="$login/$name"

python3 - "$name" "$owner" "$slug" "${stacks[@]}" <<'PY'
import re,sys,os
name,owner,slug=sys.argv[1],sys.argv[2],sys.argv[3]; stacks=sys.argv[4:]
def rw(p,fn):
    t=open(p).read(); n=fn(t)
    if n!=t: open(p,'w').write(n)
if os.path.exists('docs/README.project.md'):  # the template's README gives way to the project README
    open('README.md','w').write(open('docs/README.project.md').read().replace('{{REPO_NAME}}',name)); os.remove('docs/README.project.md')
    print('README.md: project README written for',name)
def owners(t):
    if not re.search(r'(?m)^\*\s+'+re.escape(owner)+r'\s*$',t): t=t.replace('# * @ORG/REPOSITORY-MAINTAINERS','* '+owner)
    return t
rw('.github/CODEOWNERS',owners); print('CODEOWNERS: *',owner)
p='.github/dependabot.yml'; t=open(p).read()
body,sep,tail=t.partition('# Optional additional directories')
chunks=re.split(r'(?m)(?=^  - package-ecosystem:)',body)
for i in range(len(chunks)-1):  # a block's leading comment lines sit at the end of the previous chunk; move them
    L=chunks[i].split('\n'); j=len(L)-1
    while j>0 and L[j]=='': j-=1
    k=j
    while k>=0 and L[k].startswith('  #'): k-=1
    if k<j: chunks[i]='\n'.join(L[:k+1])+'\n'; chunks[i+1]='\n'.join(L[k+1:j+1])+'\n'+chunks[i+1]
head,blocks=chunks[0],chunks[1:]
present={'npm':os.path.exists('package.json'),
 'pip':any(os.path.exists(f) for f in('requirements.txt','pyproject.toml','poetry.lock','Pipfile')),
 'github-actions':True,'terraform':any(f.endswith('.tf') for f in os.listdir('.')),'docker':os.path.exists('Dockerfile')}
kept=[];dropped=[]
for b in blocks:
    m=re.search(r'package-ecosystem:\s*"([^"]+)"',b); eco=m.group(1) if m else None
    if eco is None or present.get(eco): kept.append(b)
    else: dropped.append(eco)
open(p,'w').write((head+''.join(kept)).rstrip()+'\n\n'+sep+tail)
print('dependabot.yml: kept',', '.join(k for k,v in present.items() if v),'; dropped',', '.join(dropped) or 'nothing')
rw('.github/ISSUE_TEMPLATE/config.yml',lambda t:t.replace('ORG/REPO',slug).replace('# Replace ORG/REPO before installing this file.\n',''))
print('ISSUE_TEMPLATE/config.yml: links point at',slug)
rw('docs/TEMPLATE.md',lambda t:t.replace('{{REPO_SLUG}}',slug))
langs={'node-typescript':'javascript-typescript','python':'python'}
extra=[langs[s] for s in stacks if s in langs]
if extra:
    rw('.github/workflows/codeql.yml',lambda t:t.replace('language: [actions]','language: [actions, '+', '.join(extra)+']'))
    print('codeql.yml: languages actions,',', '.join(extra))
PY
for s in "${stacks[@]}"; do part="overlays/$s/qlty.toml.part"; [ -f "$part" ] || continue
  first="$(grep -m1 '^name = ' "$part")"
  if grep -qF "$first" .qlty/qlty.toml; then echo "qlty.toml: $s already present"
  else printf '\n' >> .qlty/qlty.toml; cat "$part" >> .qlty/qlty.toml; echo "qlty.toml: appended $s"; fi
done

if [ "$skip_github" -eq 0 ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  python3 -I -c 'import json;[print(l["name"],l["color"],l["description"],sep="\t") for l in json.load(open(".github/labels.json"))]' |
  while IFS=$'\t' read -r n c d; do gh label create "$n" --color "$c" --description "$d" --force --repo "$slug" >/dev/null && echo "label: $n"; done
  gh repo edit "$slug" --enable-discussions >/dev/null && echo "discussions: enabled on $slug"
elif [ "$skip_github" -eq 1 ]; then echo "GitHub step skipped: labels and Discussions are listed in docs/TEMPLATE.md step 2."
else
  echo "gh not available or not signed in: create the labels in .github/labels.json and enable Discussions by hand (docs/TEMPLATE.md step 2)."
fi

if [ "$prune" -eq 1 ]; then rm -rf overlays scripts; echo "pruned overlays/ and scripts/"; fi
printf '\nNext: docs/TEMPLATE.md section 2 (connect the three apps), then replace the placeholder sections in .github/SECURITY.md.\n'
