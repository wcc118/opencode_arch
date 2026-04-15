---
name: dependency-audit
description: Audits new dependencies before any install. Invoke before any pip install, npm install, or manual edit to requirements.txt, package.json, or equivalent. Build and refactor agents only.
---

# Dependency Audit

## 1 — Already Available?
```bash
pip list | grep -i {{name}} / cat requirements.txt | grep {{name}}
cat package.json | grep {{name}}
```
If already installed: use it. Do not add a duplicate.

## 2 — Version Conflicts
```bash
pip install {{pkg}}=={{ver}} --dry-run 2>&1
pip check
```
If conflicts: stop, report to orchestrator. Do not resolve autonomously.

## 3 — Vulnerabilities
```bash
safety check --package {{pkg}}=={{ver}}   # Python
npm audit                                   # Node
```
Block on HIGH/CRITICAL CVE. Proceed with warning on LOW/MEDIUM — log in `architecture.md`.

## 4 — License
| License | Status |
|---|---|
| MIT, Apache 2.0, BSD, ISC | ✅ proceed |
| LGPL | ⚠️ check linking |
| GPL, AGPL | ⚠️ tell human |
| Proprietary | ❌ stop |

## 5 — Pin and Document
```bash
echo "{{pkg}}=={{ver}}" >> requirements.txt   # or --save-exact for npm
```
Update `architecture.md` dependency table. Report result to orchestrator before installing:
```
Package: {{name}} {{version}}
Conflicts: none / [details]
CVE: none / [details]
License: {{license}} ✅/⚠️/❌
Decision: APPROVED / BLOCKED
```
