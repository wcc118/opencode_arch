---
name: github-project-sync
description: Bootstraps or adopts a project into the agent system. BOOTSTRAP: new project, no git. ADOPT: git exists, manifests missing. Invoke when agent.md and architecture.md are absent.
---

# GitHub Project Sync

## Detect Mode First
- No `.git/` → BOOTSTRAP
- `.git/` exists, no manifests → ADOPT
- Never run `git init` or `gh repo create` if `.git/` already exists

---

## BOOTSTRAP MODE

### 1 — Collect from human
`PROJECT_NAME` (kebab-case), `PURPOSE` (one sentence), `LANGUAGES`, `FRAMEWORK`, `GITHUB_USER_OR_ORG`

### 2 — Init repo
```bash
git init && git checkout -b main
gh repo create {{ORG}}/{{NAME}} --private --source=. --remote=origin --push
git checkout -b develop && git push -u origin develop && git checkout main
```
If `gh` not authenticated: pause, instruct `gh auth login`, resume.

### 3 — Pre-commit hook
Write to `.git/hooks/pre-commit` and `chmod +x`:
```bash
#!/bin/bash
TODAY=$(date +%Y%m%d)
if ! ls sessions/session_${TODAY}_*.md 1>/dev/null 2>&1; then
  echo "❌ COMMIT BLOCKED: Write a session log to sessions/ first."
  exit 1
fi
exit 0
```

### 4 — Generate .gitignore
Language-appropriate. Never add `sessions/` — logs are committed.

### 5 — Generate architecture.md
Write to project root with these sections populated from what you know:
- Project name, purpose, stack, repo URL, branch strategy
- Repository structure (run `tree -L 2`)
- Key modules table (stub with TBD)
- Dependencies table (stub with TBD)
- Decisions log (first entry: project initialized)
- Change log (first entry: bootstrap date)

### 6 — Generate agent.md
Write to project root:
```markdown
# Agent State — {{PROJECT_NAME}}
> Last: {{TIMESTAMP}} | Session: {{SESSION_ID}}

## Status
Phase: INIT | Branch: develop | Last Good SHA: {{git rev-parse HEAD}}

## Current Task
Goal: Initial project setup
In-scope files: architecture.md, agent.md
Verified (ran): —
Analyzed (read): —

## Success Criteria
- [ ] Repo accessible on GitHub [human]
- [ ] Both manifests readable [human]
- [ ] Pre-commit hook blocks commitless sessions [unit]

## Hook Status
| Hook | Status |
|---|---|
| Branch confirmed | ⬜ |
| Session log written | ⬜ |
| Commit pushed | ⬜ |

## BLOCKED
Not blocked.

## Task Queue
### Pending
(none — awaiting first task from human)

## 🔴 Next Required Action
Ask human for first task. Run task-decomposer before routing anything.

## Context Pointers
Sessions: sessions/
```

### 7 — Create sessions dir and first log
```bash
mkdir -p sessions
```
Write first session log (see session-memory skill format).

### 8 — Initial commit
```bash
git add architecture.md agent.md sessions/ .gitignore
git commit -m "chore(init): bootstrap agent system manifests"
git push origin develop
```

---

## ADOPT MODE

### 1 — Scan only (no git changes)
```bash
git remote -v && git branch -a && git log --oneline -5
git rev-parse HEAD && git branch --show-current && tree -L 2
cat package.json 2>/dev/null || cat requirements.txt 2>/dev/null || cat pyproject.toml 2>/dev/null
```

### 2 — Generate manifests from scan
Use real values throughout. Set Phase: `ADOPTED`. Last Good SHA = current HEAD. In agent.md set Next Required Action: "Ask human for first task."

### 3 — Pre-commit hook (conditional)
```bash
[ ! -f .git/hooks/pre-commit ] && # install as above
```
If hook exists: read it, note in agent.md constraints — do not overwrite.

### 4 — Sessions dir
```bash
mkdir -p sessions && [ -z "$(ls -A sessions/)" ] && touch sessions/.gitkeep
```

### 5 — Write adoption session log and commit manifests only
```bash
git add agent.md architecture.md sessions/
git commit -m "chore(agent-system): adopt existing project"
git push origin $(git branch --show-current)
```

---

## Done When
Both `agent.md` and `architecture.md` readable, `sessions/` exists with first log, pre-commit hook installed or pre-existing noted, manifests committed and pushed.
