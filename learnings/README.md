# Learning Bank

## Overview

This directory contains the continuous learning system for OpenCode.

- `memory/bank.json` — Append-only array of all session heuristics (archive)
- `memory/summary.json` — Compact (≤500 tokens objective) summary for startup injection

Heuristics are extracted automatically at session end and injected at next session startup.
Retention scoring (confidence + repetition + recency) determines which heuristics remain in the active summary vs. archived in the bank.

## Format

### bank.json
Array of objects:
```json
{
  "t": "success" | "failure",
  "p": "brief description of the pattern (≤15 words)",
  "s": "actionable guidance",
  "c": "high" | "medium" | "low",
  "ts": "ISO 8601 date (original creation)",
  "sid": "YYYYMMDD_HHMMSS (original session)",
  "rb": ["session_id", "..."],
  "lst": "ISO 8601 date (last reinforcement)"
}
```

### summary.json
```json
{
  "last_updated": "ISO 8601 date",
  "total_sessions": number,
  "heuristics": [
    {
      "t": "...",
      "p": "...",
      "s": "...",
      "c": "...",
      "ts": "...",
      "sid": "..."
    }
  ]
}
```

## Retention Model

- **Score** = base_confidence (1-3) + repetition_boost (0-3) + recency_weight (-1 to +2)
- Heuristics scoring >=7 get overflow allowance in summary (up to 1000-token threshold)
- Entries older than 90 days are evicted from summary but remain in bank.json

## Git Tracking

All files in `memory/` and `learnings/` are git-tracked in the opencode configuration repository.
