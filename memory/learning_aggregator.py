#!/usr/bin/env python3
"""
Learning Aggregator for OpenCode Continuous Learning System.
Extracts heuristics from session logs, appends to memory bank.

Features:
  - Retention scoring (confidence + repetition + recency)
  - Cross-session reinforcement tracking
  - Confidence auto-promotion on repeated reinforcement
  - Time-based decay (30/60/90 day tiers)
  - Token budget enforcement (objective ≤500, threshold ≤1000)

Usage:
    python learning_aggregator.py --session LOG_PATH
"""

import argparse
import json
import re
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(data) -> int:
    """Estimate token count from JSON data. ~4 chars per token."""
    text = json.dumps(data, separators=(',', ':'))
    return len(text) // 4


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict | list:
    """Load JSON file, return empty structure if not exists."""
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {} if path.name == 'summary.json' else []


def save_json(path: Path, data):
    """Save JSON with proper formatting."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Session log parsing
# ---------------------------------------------------------------------------

def extract_session_data(session_path: Path) -> dict:
    """Extract key data from a session log.

    Handles two formats:
      - Separate sections: '## What Worked' and '## What Failed'
      - Combined section:  '## What Worked / What Failed'
    """
    if not session_path.exists():
        raise FileNotFoundError(f"Session log not found: {session_path}")

    content = session_path.read_text(encoding='utf-8')

    worked = ""
    failed = ""

    # Try separate sections first
    worked_match = re.search(
        r'## What Worked\s*\n(.*?)(?=\n##|$)', content, re.DOTALL
    )
    failed_match = re.search(
        r'## What Failed\s*\n(.*?)(?=\n##|$)', content, re.DOTALL
    )

    if worked_match and failed_match:
        # Separate sections found
        worked = worked_match.group(1).strip()
        failed = failed_match.group(1).strip()
    else:
        # Try combined section: '## What Worked / What Failed'
        combined_match = re.search(
            r'## What Worked\s*/\s*What Failed\s*\n(.*?)(?=\n##|$)',
            content, re.DOTALL
        )
        if combined_match:
            lines = combined_match.group(1).strip().split('\n')
            worked_lines = []
            failed_lines = []
            failure_keywords = (
                'fail', 'broke', 'wrong', 'avoid', 'didn\'t',
                'error', 'miss', 'bug', 'crash', 'issue'
            )
            for line in lines:
                stripped = line.strip().lower()
                if any(kw in stripped for kw in failure_keywords):
                    failed_lines.append(line)
                elif stripped:
                    worked_lines.append(line)
            worked = '\n'.join(worked_lines)
            failed = '\n'.join(failed_lines)
        else:
            # Fallback: use whatever separate matches we found
            if worked_match:
                worked = worked_match.group(1).strip()
            if failed_match:
                failed = failed_match.group(1).strip()

    session_id = session_path.stem

    return {
        'worked': worked,
        'failed': failed,
        'session_id': session_id
    }


# ---------------------------------------------------------------------------
# Heuristic generation
# ---------------------------------------------------------------------------

def generate_heuristic(pattern: str, suggestion: str, heuristic_type: str,
                       confidence: str = "medium", session_id: str = "") -> dict:
    """Generate a heuristic object. Compact keys for token efficiency."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "t": heuristic_type,
        "p": pattern,
        "s": suggestion,
        "c": confidence,
        "ts": now,
        "sid": session_id,
        "rb": [],
        "lst": now
    }


def extract_heuristics_from_session(data: dict) -> list:
    """Extract heuristics from session worked/failed sections."""
    heuristics = []
    worked = data['worked']
    failed = data['failed']
    session_id = data['session_id']

    # Parse "What Worked" lines (each line = heuristic)
    for line in worked.split('\n'):
        line = line.strip()
        # Remove leading bullet points for pattern
        if line.startswith(('-', '*', '\u2022',
                           '1.', '2.', '3.', '4.', '5.',
                           '6.', '7.', '8.', '9.')):
            line = line[1:].strip()
            # Handle numbered lists like "1." — strip trailing dot+space
            if line and line[0] == '.':
                line = line[1:].strip()
        if not line:
            continue
        # Try to extract pattern and suggestion
        if ':' in line:
            parts = line.split(':', 1)
            pattern = parts[0].strip()
            suggestion = parts[1].strip() if len(parts) > 1 else f"Continue doing: {pattern}"
        else:
            pattern = line[:15] if len(line) > 15 else line
            suggestion = f"Repeat this success: {line}"

        heuristics.append(generate_heuristic(
            pattern=pattern,
            suggestion=suggestion,
            heuristic_type="success",
            confidence="high",
            session_id=session_id
        ))

    # Parse "What Failed" lines (each line = anti-pattern)
    for line in failed.split('\n'):
        line = line.strip()
        if line.startswith(('-', '*', '\u2022',
                           '1.', '2.', '3.', '4.', '5.',
                           '6.', '7.', '8.', '9.')):
            line = line[1:].strip()
            if line and line[0] == '.':
                line = line[1:].strip()
        if not line:
            continue
        if ':' in line:
            parts = line.split(':', 1)
            pattern = parts[0].strip()
            suggestion = parts[1].strip() if len(parts) > 1 else f"Avoid: {pattern}"
        else:
            pattern = line[:15] if len(line) > 15 else line
            suggestion = f"Avoid this failure: {line}"

        heuristics.append(generate_heuristic(
            pattern=pattern,
            suggestion=suggestion,
            heuristic_type="failure",
            confidence="medium",
            session_id=session_id
        ))

    return heuristics


# ---------------------------------------------------------------------------
# Bank operations: dedup, reinforce, migrate
# ---------------------------------------------------------------------------

def deduplicate_bank(bank: list) -> list:
    """Remove legacy duplicates from bank. Keeps earliest entry per (p, t, sid).

    Idempotent — safe to run on every invocation.
    """
    seen = {}
    cleaned = []
    for h in bank:
        key = (h['p'], h['t'], h['sid'])
        if key not in seen:
            seen[key] = True
            cleaned.append(h)
    return cleaned


def migrate_bank_schema(bank: list) -> list:
    """Add 'rb' and 'lst' fields to legacy entries that lack them."""
    for h in bank:
        if 'rb' not in h:
            h['rb'] = []
        if 'lst' not in h:
            h['lst'] = h.get('ts', datetime.now(timezone.utc).isoformat())
    return bank


def reinforce_or_append(bank: list, new_heuristics: list) -> tuple:
    """For each new heuristic, reinforce an existing entry or append as new.

    Returns (updated_bank, added_count, reinforced_count).
    """
    added = 0
    reinforced = 0
    now = datetime.now(timezone.utc).isoformat()

    for nh in new_heuristics:
        # Look for existing entry with same (pattern, type) from ANY session
        match = None
        for existing in bank:
            if existing['p'] == nh['p'] and existing['t'] == nh['t']:
                match = existing
                break

        if match is not None:
            # Same session? Skip entirely (already processed)
            if match['sid'] == nh['sid']:
                continue
            # Different session — reinforce
            if nh['sid'] not in match.get('rb', []):
                match.setdefault('rb', []).append(nh['sid'])
                match['lst'] = now
                reinforced += 1
                # Auto-promote: 3+ reinforcements upgrades medium -> high
                if len(match['rb']) >= 3 and match['c'] == 'medium':
                    match['c'] = 'high'
                    print(f"  Auto-promoted: '{match['p']}' medium -> high "
                          f"({len(match['rb'])} reinforcements)")
        else:
            # Truly new heuristic
            nh['lst'] = now
            bank.append(nh)
            added += 1

    return bank, added, reinforced


# ---------------------------------------------------------------------------
# Retention scoring and compression
# ---------------------------------------------------------------------------

def score_heuristic(h: dict, now: datetime) -> int:
    """Calculate retention score for a heuristic.

    score = base_confidence + repetition_boost + recency_weight

    base_confidence:  high=3, medium=2, low=1
    repetition_boost: min(len(reinforced_by), 3)
    recency_weight:   0-30d=+2, 31-60d=+1, 61-90d=0, 90d+=−1
    """
    # Base confidence
    conf_map = {"high": 3, "medium": 2, "low": 1}
    base = conf_map.get(h.get('c', 'low'), 1)

    # Repetition boost (capped at 3)
    rb = h.get('rb', [])
    repetition = min(len(rb), 3)

    # Recency weight — use last-seen timestamp if available
    lst_str = h.get('lst', h.get('ts', ''))
    try:
        lst = datetime.fromisoformat(lst_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        lst = now  # fallback: treat as recent

    age_days = (now - lst).days

    if age_days <= 30:
        recency = 2
    elif age_days <= 60:
        recency = 1
    elif age_days <= 90:
        recency = 0
    else:
        recency = -1

    return base + repetition + recency


def compress_heuristics(bank: list, now: datetime,
                        token_objective: int = 500,
                        token_threshold: int = 1000) -> list:
    """Compress bank into a summary list within token budget.

    1. Deduplicate by (pattern, type) — keep highest-scored entry
    2. Filter out entries older than 90 days from summary (kept in bank)
    3. Score and sort descending
    4. Fill until token_objective reached
    5. Allow overflow to token_threshold only for entries with score >= 7
    """
    # Deduplicate: keep entry with highest score per (p, t)
    best = {}
    for h in bank:
        key = (h['p'], h['t'])
        score = score_heuristic(h, now)
        if key not in best or score > best[key][1]:
            best[key] = (h, score)

    # Filter out 90+ day entries from summary
    candidates = []
    for h, score in best.values():
        lst_str = h.get('lst', h.get('ts', ''))
        try:
            lst = datetime.fromisoformat(lst_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            lst = now
        age_days = (now - lst).days
        if age_days <= 90:
            candidates.append((h, score))

    # Sort by score descending, then by timestamp descending (newer first)
    candidates.sort(key=lambda x: (x[1], x[0].get('lst', '')), reverse=True)

    # Build summary within token budget
    summary_list = []
    summary_wrapper = {"heuristics": []}

    for h, score in candidates:
        # Build a summary entry (strip rb/lst for injection — keep it lean)
        entry = {
            "t": h['t'],
            "p": h['p'],
            "s": h['s'],
            "c": h['c'],
            "ts": h['ts'],
            "sid": h['sid']
        }
        test_list = summary_list + [entry]
        summary_wrapper["heuristics"] = test_list
        tokens = estimate_tokens(summary_wrapper)

        if tokens <= token_objective:
            summary_list.append(entry)
        elif tokens <= token_threshold and score >= 7:
            # Allow overflow for high-value entries
            summary_list.append(entry)
        else:
            # Over budget — stop adding
            break

    return summary_list


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def run_git_command(cmd, repo_dir, env=None):
    """Run a git command and return success status."""
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            shell=True,
            env=env
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Git command failed: {e}")
        return False


def get_current_branch(repo_dir, env=None):
    """Detect the current git branch. Falls back to 'main'."""
    try:
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            env=env
        )
        branch = result.stdout.strip()
        return branch if branch else 'main'
    except Exception:
        return 'main'


def commit_session_log(session_path: Path, bank_path: Path,
                       summary_path: Path, repo_dir: Path = None,
                       auto_push: bool = False):
    """Auto-commit memory changes after aggregator runs."""
    if repo_dir is None:
        repo_dir = session_path.parent.parent if session_path else Path.cwd()

    session_id = (session_path.stem if session_path
                  else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))

    # Configure git identity for non-interactive commits
    git_env = os.environ.copy()
    git_env['GIT_AUTHOR_NAME'] = 'OpenCode Bot'
    git_env['GIT_AUTHOR_EMAIL'] = 'bot@opencode.local'
    git_env['GIT_COMMITTER_NAME'] = 'OpenCode Bot'
    git_env['GIT_COMMITTER_EMAIL'] = 'bot@opencode.local'

    # Step 1: Stage files
    files_to_stage = [str(bank_path), str(summary_path)]
    if session_path and session_path.exists():
        files_to_stage.append(str(session_path))

    stage_cmd = ['git', 'add'] + files_to_stage
    if run_git_command(stage_cmd, str(repo_dir), env=git_env):
        print(f"Staged files: {', '.join(files_to_stage)}")
    else:
        print("Warning: Failed to stage files")
        return False

    # Step 2: Commit
    commit_cmd = [
        'git', 'commit', '-m',
        f'chore(memory): archive session {session_id}'
    ]
    if run_git_command(commit_cmd, str(repo_dir), env=git_env):
        print(f"Committed: chore(memory): archive session {session_id}")
    else:
        status_check = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            env=git_env
        )
        if not status_check.stdout.strip():
            print("No changes to commit")
        else:
            print("Warning: Commit failed")
        return False

    # Step 3: Auto-push if requested — detect current branch
    if auto_push:
        branch = get_current_branch(str(repo_dir), env=git_env)
        push_cmd = ['git', 'push', 'origin', branch]
        if run_git_command(push_cmd, str(repo_dir), env=git_env):
            print(f"Pushed to origin/{branch}")
        else:
            print("Warning: Push failed (may need to configure remote "
                  "or authenticate)")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='OpenCode Learning Aggregator'
    )
    parser.add_argument('--session', type=str, required=True,
                        help='Path to session log')
    parser.add_argument('--bank', type=str, default='memory/bank.json',
                        help='Path to bank.json')
    parser.add_argument('--summary', type=str, default='memory/summary.json',
                        help='Path to summary.json')
    parser.add_argument('--auto-commit', action='store_true',
                        help='Auto-commit changes')
    parser.add_argument('--auto-push', action='store_true',
                        help='Auto-push after commit (requires --auto-commit)')
    args = parser.parse_args()

    session_path = Path(args.session)
    bank_path = Path(args.bank)
    summary_path = Path(args.summary)
    repo_dir = (Path(args.session).parent.parent
                if session_path else Path.cwd())
    now = datetime.now(timezone.utc)

    # Load current state
    bank = load_json(bank_path)
    summary = load_json(summary_path)

    # Migrate legacy entries (add rb/lst fields if missing)
    bank = migrate_bank_schema(bank)

    # Deduplicate legacy duplicates (idempotent)
    before_dedup = len(bank)
    bank = deduplicate_bank(bank)
    if len(bank) < before_dedup:
        print(f"Cleaned {before_dedup - len(bank)} legacy duplicate(s) "
              f"from bank")

    # Extract session data
    print(f"Reading session: {session_path}")
    session_data = extract_session_data(session_path)

    # Generate heuristics from session
    new_heuristics = extract_heuristics_from_session(session_data)
    print(f"Extracted {len(new_heuristics)} heuristic(s) from session")

    # Reinforce existing or append new
    bank, added, reinforced = reinforce_or_append(bank, new_heuristics)
    print(f"Added {added} new, reinforced {reinforced} existing")

    # Save bank
    save_json(bank_path, bank)

    # Update summary with retention-scored compression
    compressed = compress_heuristics(bank, now,
                                     token_objective=500,
                                     token_threshold=1000)

    # Derive total_sessions from bank data (not incremented blindly)
    all_sessions = set()
    for h in bank:
        all_sessions.add(h['sid'])
        for rsid in h.get('rb', []):
            all_sessions.add(rsid)

    summary['last_updated'] = now.isoformat()
    summary['total_sessions'] = len(all_sessions)
    summary['heuristics'] = compressed
    save_json(summary_path, summary)

    # Report
    token_count = estimate_tokens(summary)
    print(f"\n[OK] Bank: {len(bank)} entries "
          f"({added} new, {reinforced} reinforced)")
    print(f"Summary: {len(compressed)} heuristics, "
          f"~{token_count} tokens, "
          f"{summary['total_sessions']} session(s) tracked")

    if token_count > 500:
        print(f"[WARN] Summary exceeds 500-token objective "
              f"({token_count} tokens)")
    if token_count > 1000:
        print(f"[ERROR] Summary exceeds 1000-token hard threshold!")

    # Auto-commit if requested
    if args.auto_commit:
        commit_session_log(session_path, bank_path, summary_path,
                           repo_dir, args.auto_push)


if __name__ == '__main__':
    main()
