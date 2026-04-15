---
name: rollback-recovery
description: Recovers a bricked build or unrecoverable branch. Invoke when build fails completely after a commit, all tests fail after a change, or 3 consecutive error attempts have failed. Orchestrator only.
---

# Rollback Recovery

**Never touch main. Never force-push a shared branch.**

## 1 — Preserve Evidence
```bash
git diff HEAD > /tmp/rollback_{{timestamp}}.patch
git log --oneline -10 > /tmp/rollback_{{timestamp}}_log.txt
```

## 2 — Choose Strategy

| Situation | Strategy |
|---|---|
| Uncommitted changes broke it | `git stash push -m "rollback-{{timestamp}}"` |
| Last 1-2 commits broke it | `git revert {{sha}}..HEAD --no-commit && git commit` |
| Branch is unrecoverable | Abandon, restart from develop |
| Main affected | **STOP. Tell human immediately. Do not touch main.** |

## 3 — Verify Recovery
Run build + full test suite. If still failing: stop, set Phase BLOCKED with resolution condition, tell human. Do not attempt further automated recovery.

## 4 — Fix Forward
```bash
git checkout -b fix/{{what-broke}}
```
Write bug to agent.md with file, line, expected vs actual. Route to `@debug` with evidence files before any fix attempt.

## 5 — Update agent.md
```
Phase: BUILDING
Last Good SHA: {{recovered SHA}}
BLOCKED: not blocked
Next Required Action: Route {{bug description}} to @debug on fix/{{branch}}
```
Write session log entry with rollback event. Tell human what happened.
