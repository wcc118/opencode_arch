# Learning Bank

## Overview

This directory contains the continuous learning system for OpenCode.

- `memory/bank.json` — Append-only array of all session heuristics
- `memory/summary.json` — Compact (≤300 tokens) summary for startup injection
- `learnings/monthly.md` — Human-readable monthly summaries

Heuristics are extracted automatically at session end and injected at next session startup.

## Format

### bank.json
Array of objects:
```json
{
  "type": "success" | "failure",
  "pattern": "brief description of the pattern (≤15 words)",
  "suggestion": "actionable guidance",
  "confidence": "high" | "medium" | "low",
  "timestamp": "ISO 8601 date",
  "session_id": "YYYYMMDD_HHMMSS"
}
```

### summary.json
```json
{
  "last_updated": "ISO 8601 date",
  "total_sessions": number,
  "heuristics": [
    {
      "type": "...",
      "pattern": "...",
      "suggestion": "...",
      "confidence": "..."
    }
  ]
}
```

## Git Tracking

All files in `memory/` and `learnings/` are git-tracked in `github.com/wcc118/opencode_arch`.
