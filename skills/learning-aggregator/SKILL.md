---
name: learning-aggregator
description: Extracts heuristics from session logs, appends to memory bank. Invoke at session end (BLOCKED/COMPLETE/HANDOFF).
---

# Learning Aggregator

## Steps
1. Read session log(s) — single file via `--session` or batch discovery via `--scan`
2. Extract "What Worked" / "What Failed" sections using state machine parser:
   - Format 1/2: Separate `## What Worked` and `## What Failed` sections
   - Format 3: Combined `## What Worked / What Failed` with `### ` sub-headers
   - All markdown headers filtered out (never become heuristics)
3. For each content line, generate heuristic JSON objects:
   - Success: `{"t": "success", "p": "<full line>", "np": "<normalized>", "s": "Do: <line>", "c": "high", ...}`
   - Failure: `{"t": "failure", "p": "<full line>", "np": "<normalized>", "s": "Avoid: <line>", "c": "medium", ...}`
4. Reinforce existing bank entries via normalized pattern matching (`np` field) or append new
5. Compress bank into `memory/summary.json` using retention scoring within token budget

## Heuristic Schema
```json
{
  "t": "success|failure",
  "p": "Full human-readable pattern (up to 120 chars)",
  "np": "normalized lowercase pattern for cross-session matching",
  "s": "Do: ... | Avoid: ...",
  "c": "high|medium|low",
  "ts": "ISO timestamp",
  "sid": "session_id",
  "rb": ["reinforcing_session_ids"],
  "lst": "last-seen timestamp"
}
```

## Retention Scoring

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

Matching uses **normalized patterns** (`np` field) — lowercased, parentheticals removed, contractions expanded, whitespace collapsed. When a new session generates a heuristic matching an existing `(np, type)`:
- The existing entry's `rb` array gains the new session_id
- The `lst` timestamp updates to now
- No duplicate entry is created
- **Auto-promotion**: 3+ reinforcements from different sessions promotes `medium` → `high`

## Time-Based Decay

| Age | Behavior |
|-----|----------|
| 0-30 days | Full retention |
| 31-60 days | Must have score ≥ 3 |
| 61-90 days | Must have score ≥ 5 |
| 90+ days | Evicted from summary.json (kept in bank.json) |

## Token Budget

- **Objective**: ≤500 tokens in summary.json
- **Hard threshold**: ≤1000 tokens (overflow only for score ≥ 7)

## Implementation

Single session:
```bash
python C:/Users/wcc11/.config/opencode/memory/learning_aggregator.py \
  --session <session_log> \
  --bank C:/Users/wcc11/.config/opencode/memory/bank.json \
  --summary C:/Users/wcc11/.config/opencode/memory/summary.json
```

Batch scan (discovers all unprocessed sessions):
```bash
python C:/Users/wcc11/.config/opencode/memory/learning_aggregator.py \
  --scan C:/Users/wcc11/.config/opencode \
  --scan G:/Projects/CashFlow \
  --bank C:/Users/wcc11/.config/opencode/memory/bank.json \
  --summary C:/Users/wcc11/.config/opencode/memory/summary.json
```

Fine-tuning export:
```bash
python C:/Users/wcc11/.config/opencode/memory/export_training_data.py \
  --bank C:/Users/wcc11/.config/opencode/memory/bank.json \
  --sessions-dir C:/Users/wcc11/.config/opencode/sessions \
  --output-dir C:/Users/wcc11/.config/opencode/memory/training \
  --formats all
```

## Output
- Processed N new session(s), skipped M already-processed
- Bank: X entries (Y new, Z reinforced)
- Summary: N heuristics, ~T tokens, S session(s) tracked
- Training: N heuristic pairs, M session narratives, K corrective pairs, J DPO pairs
