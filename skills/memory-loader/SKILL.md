---
name: memory-loader
description: Reads summary.json, injects heuristics into context at session startup.
---

# Memory Loader

## Run at Startup
1. Read `memory/summary.json`
2. Inject heuristics as system prompt preface (≤300 tokens)
3. Continue with session

## Keep Injected
- heuristics only — no bank.json content
