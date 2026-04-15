---
name: learning-aggregator
description: Extracts heuristics from session logs, appends to memory bank. Invoke at session end (BLOCKED/COMPLETE/HANDOFF).
---

# Learning Aggregator

## Steps
1. Read most recent session log from `sessions/session_YYYYMMDD_HHMMSS.md`
2. Extract "What Worked / What Failed" line → compress into heuristics JSON
3. Append to `memory/bank.json` (array of objects)
4. Update `memory/summary.json` heuristics array to reflect new entries

## Output (to agent.md or human)
- Appended X heuristic(s) to bank
- Summary updated
