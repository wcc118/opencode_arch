---
name: memory-loader
description: Reads summary.json, injects heuristics into context at session startup.
---

# Memory Loader

## Run at Startup
1. Read `memory/summary.json` from `C:/Users/wcc11/.config/opencode/memory/summary.json`
2. Extract `heuristics` array
3. **Validate & filter** — skip any heuristic where:
   - Pattern (`p`) starts with `#` (markdown headers that leaked through)
   - Pattern (`p`) is ≤15 characters AND contains no space (truncation artifacts)
   - Suggestion (`s`) starts with `"Repeat this success: ###"` or `"Avoid this failure: ###"` (header echoes)
   - Suggestion (`s`) is a parenthetical fragment (starts with lowercase, ends with `)`)
   - Pattern (`p`) or Suggestion (`s`) is empty
4. **Quality gate** — if fewer than 2 valid heuristics remain after filtering, log:
   ```
   [WARN] Memory injection: only {N} valid heuristics after filtering. Bank may need re-aggregation.
   ```
5. Inject as **system prompt preface** (≤500 tokens objective, ≤1000 tokens hard threshold) in this format:

```
## Learned Heuristics ({N} from {S} sessions)

### Successes (repeat these)
- {pattern} → {suggestion} [{session_id}]

### Failures (avoid these)
- {pattern} → {suggestion} [{session_id}]
```

Group by type (successes first, then failures). Drop timestamps — the model doesn't need them. Keep session_id for traceability.

6. Continue with session with heuristics injected

## Keep Injected
- heuristics only — no bank.json content
- Entries are pre-scored by retention score (confidence + repetition + recency)
- Trim lowest-scored entries to stay ≤500 tokens; hard limit 1000 tokens

## File Roles
| File | Purpose |
|------|---------|
| `memory/summary.json` | Runtime injection payload (small, ≤500 tokens) |
| `memory/bank.json` | Full archive (all heuristics ever, with reinforcement tracking) |
| `memory/training/finetune_data.jsonl` | Fine-tuning export (instruction/input/output format, see `memory/export_training_data.py`) |

The three files serve different purposes: **injection**, **archive**, **training**. Only `summary.json` is read at startup.
