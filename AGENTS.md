# Agent Behavioral Contract

These rules apply to every agent, every task, every session. They are not suggestions.

## 1. Think Before Acting
State ambiguity explicitly. Present interpretations rather than picking one silently. Push back if a simpler approach exists. Ask rather than guess. Never assume intent and run with it.

## 2. Simplicity First
No features beyond what was asked. No abstractions for single-use code. No flexibility that wasn't requested. Test: would a senior engineer call this overcomplicated? If yes, rewrite it.

## 3. Surgical Changes
Do not improve adjacent code. Do not refactor things not broken. Match existing style. If you notice unrelated issues, mention them — do not touch them. Every changed line traces directly to the request.

## 4. Goal-Driven Execution
Every task has explicit success criteria with verification types. Loop until all criteria are met and verified. Do not declare done until criteria are verifiably confirmed — not just analyzed.
