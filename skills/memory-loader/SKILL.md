---
name: memory-loader
description: Reads summary.json, injects heuristics into context at session startup.
---

# Memory Loader

## Run at Startup
1. Read `memory/summary.json` from `C:/Users/wcc11/.config/opencode/memory/summary.json`
2. Extract `heuristics` array
3. Inject as **system prompt preface** (≤500 tokens objective, ≤1000 tokens hard threshold) in this compact format:

```
## Memory Heuristics (past sessions)
- <type>: <pattern> → <suggestion> (confidence: <confidence>)
  [timestamp: <timestamp>, session: <session_id>]
```

Compact keys: t=type, p=pattern, s=suggestion, c=confidence, ts=timestamp, sid=session_id

4. Continue with session with heuristics injected

## Keep Injected
- heuristics only — no bank.json content
- Entries are pre-scored by retention score (confidence + repetition + recency)
- Trim lowest-scored entries to stay ≤500 tokens; hard limit 1000 tokens
