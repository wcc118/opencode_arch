---
name: learning-aggregator
description: Extracts heuristics from session logs, appends to memory bank. Invoke at session end (BLOCKED/COMPLETE/HANDOFF).
---

# Learning Aggregator

## Steps
1. Read most recent session log from `sessions/session_*.md`
2. Extract "What Worked" / "What Failed" sections (handles both separate and combined formats)
3. For each line, generate heuristic JSON objects:
   - Success: `{"t": "success", "p": "<pattern>", "s": "Repeat...", "c": "high", "ts": "...", "sid": "..."}`
   - Failure: `{"t": "failure", "p": "<pattern>", "s": "Avoid...", "c": "medium", "ts": "...", "sid": "..."}`
4. Reinforce existing bank entries or append new ones
5. Compress bank into `memory/summary.json` using retention scoring within token budget

## Retention Scoring

Each heuristic receives a retention score at compression time:

```
score = base_confidence + repetition_boost + recency_weight
```

| Factor | Calculation |
|--------|------------|
| base_confidence | high=3, medium=2, low=1 |
| repetition_boost | +1 per cross-session reinforcement, capped at +3 |
| recency_weight | 0-30d=+2, 31-60d=+1, 61-90d=0, 90d+=−1 |

Score range: 0 to 9.

## Reinforcement

When a new session generates a heuristic matching an existing bank entry's `(pattern, type)`:
- The existing entry's `rb` (reinforced_by) array gains the new session_id
- The `lst` (last-seen timestamp) updates to now
- No duplicate entry is created
- **Auto-promotion**: 3+ reinforcements from different sessions promotes `medium` → `high`

## Time-Based Decay

| Age | Behavior |
|-----|----------|
| 0-30 days | Full retention. All heuristics kept unless over budget. |
| 31-60 days | Must have score ≥ 3 to survive compression. |
| 61-90 days | Must have score ≥ 5 to survive. |
| 90+ days | Evicted from summary.json. Remains in bank.json as archive. |

## Token Budget

- **Objective**: ≤500 tokens in summary.json
- **Hard threshold**: ≤1000 tokens (overflow allowed only for entries scoring ≥ 7)
- Enforced during compression via `estimate_tokens()`

## Implementation
Run: `python C:/Users/wcc11/.config/opencode/memory/learning_aggregator.py --session <session_log> --bank C:/Users/wcc11/.config/opencode/memory/bank.json --summary C:/Users/wcc11/.config/opencode/memory/summary.json`

## Output (to agent.md or human)
- Added X new, reinforced Y existing
- Summary: N heuristics, ~T tokens, S session(s) tracked
