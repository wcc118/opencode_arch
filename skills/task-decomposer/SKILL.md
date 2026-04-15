---
name: task-decomposer
description: Breaks a goal into atomic, verifiable subtasks before any agent begins work. Invoke for any task with more than one moving part. Each subtask gets explicit success criteria with verification types and an in-scope file list.
---

# Task Decomposer

## Before Decomposing
Answer these or ask the human:
1. What does done look like? (end state, not process)
2. What must not change?
3. What files are in play?

## A Good Subtask
- Has binary success criteria — passes or it doesn't
- Has an explicit verification type on every criterion
- Has an explicit in-scope file list — nothing outside it gets touched
- Completable in one session by one agent

## Output Format — Required for Every Subtask
```
Subtask N: {{name}}
Agent: {{agent}}
Branch: feature/{{slug}} or fix/{{slug}}
Depends on: subtask N-1 / none
In-scope files: [explicit list — everything not listed is out of scope]

Success criteria:
  - {{criterion}} [unit]
  - {{criterion}} [runtime]
  - {{criterion}} [human]

Out of scope: {{what this explicitly does not do}}
```

## Verification Types
- `[unit]` — pytest or equivalent must execute and pass
- `[runtime]` — code must actually run, not just pass unit tests
- `[human]` — explicit human confirmation required before marking done

## Sizing Rule
If you can't write a single success criterion: split it. If it touches more than 3 files: consider splitting. If it can't be done in one session: split it.

## Write to agent.md
Add subtasks to task queue (names only in queue — full detail lives in the subtask definition). Set first subtask In Progress. Update Next Required Action. Set in-scope files in Current Task block.
