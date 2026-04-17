# Architecture — opencode_arch

## Purpose
Continuous learning retention system for OpenCode AI agent framework. Extracts heuristics from session logs, scores them by confidence/repetition/recency, and injects relevant learnings into new sessions at startup.

## Stack
- **Runtime**: OpenCode AI (Node.js plugin framework)
- **Languages**: Python 3.11+ (aggregator, token counter), Markdown (agents, skills)
- **Models**: Qwen3-Coder-Next FP8 (primary, DGX Spark), Qwen2.5-Coder 7B (small), Qwen3-VL 8B (vision)
- **Repository**: https://github.com/wcc118/opencode_arch.git
- **Branch strategy**: `master` (single branch, human-approved merges)

## Repository Structure

```
opencode_arch/
├── AGENTS.md                    # Agent behavioral contract (all agents)
├── session.md                   # Session state tracking manifest
├── architecture.md              # This file
├── opencode.json                # OpenCode config (models, providers)
├── package.json                 # Node.js dependencies
├── agents/
│   ├── orchestrator.md          # Session lifecycle, task routing, git ops
│   ├── build.md                 # Feature implementation agent
│   ├── analysis.md              # Planning and code review (read-only)
│   ├── debug.md                 # Error diagnosis (read-only)
│   ├── docs.md                  # Documentation generation
│   ├── explore.md               # Codebase navigation (read-only)
│   ├── refactor.md              # Code structure improvement
│   ├── test.md                  # Test writing and execution
│   └── vision.md                # Image/diagram analysis (read-only)
├── skills/
│   ├── memory-loader/SKILL.md   # Startup heuristic injection
│   ├── learning-aggregator/SKILL.md  # Session-end heuristic extraction
│   ├── session-memory/SKILL.md  # Session log writing + context management
│   ├── task-decomposer/SKILL.md # Goal → subtask breakdown
│   ├── dependency-audit/SKILL.md # Pre-install dependency check
│   ├── rollback-recovery/SKILL.md # Build failure recovery
│   └── github-project-sync/SKILL.md # Project bootstrap/adoption
├── memory/
│   ├── bank.json                # Append-only heuristic archive
│   ├── summary.json             # Compressed injection payload (≤500 tokens)
│   ├── learning_aggregator.py   # Extraction, scoring, compression engine
│   └── count_tokens.py          # Token budget estimation utility
├── sessions/
│   └── session_*.md             # Session logs (git-tracked)
└── learnings/
    └── README.md                # Learning system documentation
```

## Key Modules

| Module | Purpose | Entry Point |
|--------|---------|-------------|
| Learning Aggregator | Extract heuristics, score, compress, reinforce | `memory/learning_aggregator.py` |
| Token Counter | Estimate summary.json token budget | `memory/count_tokens.py` |
| Memory Loader | Inject heuristics at session startup | `skills/memory-loader/SKILL.md` |
| Orchestrator | Session lifecycle, agent routing | `agents/orchestrator.md` |

## Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| @opencode-ai/plugin | 1.4.3 | OpenCode plugin framework | — |
| Python 3.11+ | stdlib only | Aggregator runtime (no pip dependencies) | PSF |

## Memory System

### Data Flow
```
Session Log → learning_aggregator.py → bank.json (append) → compress → summary.json
                                                                          ↓
                                                               memory-loader skill
                                                                          ↓
                                                              Next session startup
```

### Retention Scoring
```
score = base_confidence(1-3) + repetition_boost(0-3) + recency_weight(-1 to +2)
```

- **Token budget**: ≤500 tokens objective, ≤1000 hard threshold
- **Reinforcement**: Cross-session pattern matches increment `rb` array
- **Auto-promotion**: 3+ reinforcements promotes medium → high confidence
- **Decay tiers**: 0-30d full, 31-60d score≥3, 61-90d score≥5, 90d+ evicted from summary

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-15 | Document-based architecture (markdown skills) | Integrates cleanly with OpenCode's existing framework |
| 2026-04-15 | Compact JSON keys (t, p, s, c, ts, sid) | Token efficiency for context injection |
| 2026-04-15 | Git-tracked memory bank | Cross-machine persistence without external services |
| 2026-04-17 | Retention scoring with time-based decay | Prevents unbounded growth, rewards repeated patterns |
| 2026-04-17 | chars/4 token estimation | Avoids tokenizer dependency, sufficient accuracy with 2x budget headroom |
| 2026-04-17 | Archive in bank, evict from summary at 90d | Preserves institutional memory while keeping injection lean |
| 2026-04-17 | Exact pattern match for reinforcement | Deterministic, no false positives |
| 2026-04-17 | Auto-promote on 3+ reinforcements | Earned trust model — repeated lessons gain confidence |

## Change Log

| Date | Change | SHA |
|------|--------|-----|
| 2026-04-15 | Initial commit with agents and skills | a9fb8b7 |
| 2026-04-15 | Add continuous learning memory bank | 91cd285 |
| 2026-04-15 | Add continuous learning retention system | f93476d |
| 2026-04-17 | System health review: fix 13 bugs, add retention scoring, create manifests | pending |
