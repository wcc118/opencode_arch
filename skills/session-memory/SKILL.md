---
name: session-memory
description: Writes session logs to disk and manages context window. Invoke after every 2 subtasks, before every commit, and immediately if OpenCode compaction has triggered more than once. Merges checkpoint and context management into one skill.
---

# Session Memory

## Session Log — Write Before Every Commit
Write to `sessions/session_YYYYMMDD_HHMMSS.md`:
```markdown
# Session — {{TIMESTAMP}}
Agent: {{name}} | Branch: {{branch}} | SHA: {{sha}}

## Done
{{ordered list: file/function changed, one line each}}

## Decisions
{{decision: rationale — one line each}}

## Verified vs Analyzed
Verified (ran): [criteria confirmed by execution]
Analyzed (read): [criteria confirmed by code review only]

## What Worked / What Failed
{{concrete — specific enough that a model could learn from it}}

## Skill Improvements Noticed
{{anything that would make agent or skill files better}}

## Open Items / BLOCKED conditions
{{what next session picks up, one per line}}
{{any BLOCKED resolution conditions outstanding}}

## Handoff
Next action: {{one sentence}}
Phase: {{BUILDING / BLOCKED / HANDOFF / COMPLETE}}
```

## Rules
- Be concrete: "Fixed `verify_token()` raising `KeyError` when `exp` missing" not "fixed auth bug"
- Verified vs Analyzed section is mandatory — never leave both blank
- Pre-commit hook blocks commits without today's log
- Skill Improvements section feeds the system's own improvement loop — always fill it

---

## Context Window Management

### After Every 2 Subtasks — Always
1. Write session log to disk
2. Drop all file contents from context — filenames only
3. Re-read `agent.md` only before continuing
4. Do not re-read `architecture.md` unless next task requires it

### Thresholds

| Signal | Action |
|---|---|
| 2 subtasks complete | Write log, drop context, re-anchor |
| Uncertain about earlier decisions | Re-read agent.md immediately, do not guess |
| OpenCode compaction triggered once | Write log now, treat as 75% threshold |
| OpenCode compaction triggered twice | Hard stop — compaction loop |

### Hard Stop (compaction loop or 75%+ context)
1. Write minimal state to agent.md Next Required Action only (keep it short — long writes trigger another loop)
2. Commit any completable work
3. Tell human: "Context critical. State saved in agent.md. Start fresh session."

### Re-Anchor After Any Context Drop
Before continuing: confirm from agent.md — active task, branch, in-scope files, next action. If any unclear: re-read agent.md. Do not guess.
