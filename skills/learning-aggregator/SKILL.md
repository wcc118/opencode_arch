---
name: learning-aggregator
description: Extracts heuristics from session logs, appends to memory bank. Invoke at session end (BLOCKED/COMPLETE/HANDOFF).
---

# Learning Aggregator

## Steps
1. Read most recent session log from `sessions/session_*.md`
2. Extract "What Worked / What Failed" sections
3. For each line in those sections, generate heuristic JSON objects:
   - Success: `{"type": "success", "pattern": "<pattern>", "suggestion": "Repeat...", "confidence": "high", "timestamp": "...", "session_id": "..."}`
   - Failure: `{"type": "failure", "pattern": "<pattern>", "suggestion": "Avoid...", "confidence": "medium", "timestamp": "...", "session_id": "..."}`
4. Append heuristics to `C:/Users/wcc11/.config/opencode/memory/bank.json`
5. Compress heuristics (top 5 by confidence) into `memory/summary.json`

## Implementation
Run: `python C:/Users/wcc11/.config/opencode/memory/learning_aggregator.py --session <session_log> --bank C:/Users/wcc11/.config/opencode/memory/bank.json --summary C:/Users/wcc11/.config/opencode/memory/summary.json`

## Output (to agent.md or human)
- Appended X heuristic(s) to bank
- Summary updated with top <N> heuristics
