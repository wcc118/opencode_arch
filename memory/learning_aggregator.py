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
  - Batch session discovery and aggregation via --scan

Usage:
    python learning_aggregator.py --session LOG_PATH --bank ... --summary ...
    python learning_aggregator.py --scan DIR [--scan DIR2] --bank ... --summary ...
"""

import argparse
import glob as globmod
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

def _strip_header_lines(text: str) -> str:
    """Remove any lines starting with '#' from output text."""
    return '\n'.join(
        line for line in text.split('\n')
        if not line.strip().startswith('#')
    ).strip()


def extract_session_data(session_path: Path) -> dict:
    """Extract key data from a session log.

    Handles three formats:
      - Format 1/2: Separate '## What Worked' and '## What Failed' sections
      - Format 3:   Combined '## What Worked / What Failed' with ### sub-headers
        parsed via a state machine (not keyword matching)

    All markdown headers (lines starting with #) are stripped from output.
    """
    if not session_path.exists():
        raise FileNotFoundError(f"Session log not found: {session_path}")

    content = session_path.read_text(encoding='utf-8')

    worked = ""
    failed = ""

    # Try separate sections first (Format 1 and 2)
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
        # Try combined section: '## What Worked / What Failed' (Format 3)
        combined_match = re.search(
            r'## What Worked\s*/\s*What Failed\s*\n(.*?)(?=\n## |\Z)',
            content, re.DOTALL
        )
        if combined_match:
            lines = combined_match.group(1).split('\n')
            worked_lines = []
            failed_lines = []
            state = "unknown"  # state machine: unknown | worked | failed

            for line in lines:
                stripped = line.strip()
                # Detect sub-header state transitions
                if re.match(r'^###\s+What Worked', stripped, re.IGNORECASE):
                    state = "worked"
                    continue  # header is a transition, not content
                if re.match(r'^###\s+What Failed', stripped, re.IGNORECASE):
                    state = "failed"
                    continue  # header is a transition, not content
                # Skip any other markdown headers
                if stripped.startswith('#'):
                    continue
                # Non-empty content lines go to current state bucket
                if stripped:
                    if state == "worked":
                        worked_lines.append(line)
                    elif state == "failed":
                        failed_lines.append(line)
                    else:
                        # No sub-headers seen yet — safe default: worked
                        worked_lines.append(line)

            worked = '\n'.join(worked_lines).strip()
            failed = '\n'.join(failed_lines).strip()
        else:
            # Fallback: use whatever separate matches we found
            if worked_match:
                worked = worked_match.group(1).strip()
            if failed_match:
                failed = failed_match.group(1).strip()

    # Final filter: strip any remaining markdown header lines from output
    worked = _strip_header_lines(worked)
    failed = _strip_header_lines(failed)

    session_id = session_path.stem

    return {
        'worked': worked,
        'failed': failed,
        'session_id': session_id
    }


# ---------------------------------------------------------------------------
# Heuristic generation
# ---------------------------------------------------------------------------

def normalize_pattern(text: str) -> str:
    """Normalize a pattern string for fuzzy cross-session matching.

    - Lowercases
    - Strips leading/trailing whitespace
    - Removes backticks and parentheticals (...)
    - Removes markdown bold (**) and italic (_) formatting
    - Normalizes dashes (em-dash, en-dash) to spaces
    - Expands common contractions
    - Strips leading/trailing punctuation
    - Collapses multiple spaces to single
    - Truncates to 120 chars
    """
    text = text.strip().lower()
    # Remove backticks
    text = text.replace('`', '')
    # Remove markdown bold/italic: **bold** -> bold, _italic_ -> italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)
    # Remove parentheticals
    text = re.sub(r'\([^)]*\)', '', text)
    # Normalize em-dash and en-dash to space
    text = text.replace('\u2014', ' ')   # em-dash —
    text = text.replace('\u2013', ' ')   # en-dash –
    # Expand common contractions
    text = text.replace("won't", "will not")
    text = text.replace("can't", "cannot")
    text = text.replace("didn't", "did not")
    text = text.replace("doesn't", "does not")
    text = text.replace("isn't", "is not")
    text = text.replace("aren't", "are not")
    text = text.replace("wasn't", "was not")
    text = text.replace("weren't", "were not")
    text = text.replace("don't", "do not")
    text = text.replace("couldn't", "could not")
    text = text.replace("shouldn't", "should not")
    text = text.replace("wouldn't", "would not")
    # Remove surrounding quotes
    text = re.sub(r'["\u201c\u201d]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Strip leading/trailing punctuation (periods, commas, semicolons)
    text = text.strip('.,;:')
    text = text.strip()
    return text[:120]


def generate_heuristic(pattern: str, suggestion: str, heuristic_type: str,
                       confidence: str = "medium", session_id: str = "",
                       normalized_pattern: str = "") -> dict:
    """Generate a heuristic object. Compact keys for token efficiency."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "t": heuristic_type,
        "p": pattern,
        "np": normalized_pattern or normalize_pattern(pattern),
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
        # Skip markdown headers and horizontal rules
        if line.startswith('#') or re.match(r'^-{2,}$', line) or re.match(r'^\*{2,}$', line):
            continue
        # Remove leading bullet points for pattern
        if line.startswith(('-', '*', '\u2022',
                           '1.', '2.', '3.', '4.', '5.',
                           '6.', '7.', '8.', '9.')):
            line = line[1:].strip()
            # Handle numbered lists like "1." — strip trailing dot+space
            if line and line[0] == '.':
                line = line[1:].strip()
        if not line or len(line) < 5:
            continue
        # Full line as pattern (up to 120 chars), no colon splitting
        pattern = line[:120]
        suggestion = f"Do: {line}"

        heuristics.append(generate_heuristic(
            pattern=pattern,
            suggestion=suggestion,
            heuristic_type="success",
            confidence="high",
            session_id=session_id,
            normalized_pattern=normalize_pattern(line)
        ))

    # Parse "What Failed" lines (each line = anti-pattern)
    for line in failed.split('\n'):
        line = line.strip()
        # Skip markdown headers and horizontal rules
        if line.startswith('#') or re.match(r'^-{2,}$', line) or re.match(r'^\*{2,}$', line):
            continue
        if line.startswith(('-', '*', '\u2022',
                           '1.', '2.', '3.', '4.', '5.',
                           '6.', '7.', '8.', '9.')):
            line = line[1:].strip()
            if line and line[0] == '.':
                line = line[1:].strip()
        if not line or len(line) < 5:
            continue
        # Full line as pattern (up to 120 chars), no colon splitting
        pattern = line[:120]
        suggestion = f"Avoid: {line}"

        heuristics.append(generate_heuristic(
            pattern=pattern,
            suggestion=suggestion,
            heuristic_type="failure",
            confidence="medium",
            session_id=session_id,
            normalized_pattern=normalize_pattern(line)
        ))

    return heuristics


# ---------------------------------------------------------------------------
# Bank operations: dedup, reinforce, migrate
# ---------------------------------------------------------------------------

def deduplicate_bank(bank: list) -> list:
    """Remove legacy duplicates from bank. Keeps earliest entry per (np, t, sid).

    Idempotent — safe to run on every invocation.
    """
    seen = {}
    cleaned = []
    for h in bank:
        np = h.get('np', normalize_pattern(h['p']))
        key = (np, h['t'], h['sid'])
        if key not in seen:
            seen[key] = True
            cleaned.append(h)
    return cleaned


def migrate_bank_schema(bank: list) -> list:
    """Add 'rb', 'lst', and 'np' fields to legacy entries that lack them."""
    for h in bank:
        if 'rb' not in h:
            h['rb'] = []
        if 'lst' not in h:
            h['lst'] = h.get('ts', datetime.now(timezone.utc).isoformat())
        if 'np' not in h:
            h['np'] = normalize_pattern(h.get('p', ''))
    return bank


def reinforce_or_append(bank: list, new_heuristics: list) -> tuple:
    """For each new heuristic, reinforce an existing entry or append as new.

    Returns (updated_bank, added_count, reinforced_count).
    """
    added = 0
    reinforced = 0
    now = datetime.now(timezone.utc).isoformat()

    for nh in new_heuristics:
        # Look for existing entry with same (normalized pattern, type) from ANY session
        match = None
        nh_np = nh.get('np', normalize_pattern(nh['p']))
        for existing in bank:
            existing_np = existing.get('np', normalize_pattern(existing['p']))
            if existing_np == nh_np and existing['t'] == nh['t']:
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
    # Deduplicate: keep entry with highest score per (np, t)
    best = {}
    for h in bank:
        np = h.get('np', normalize_pattern(h['p']))
        key = (np, h['t'])
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
# Batch session discovery
# ---------------------------------------------------------------------------

def discover_sessions(scan_dirs: list, processed: list) -> list:
    """Find all session_*.md files under scan_dirs, excluding already-processed.

    Globs for **/sessions/session_*.md under each directory, filters out paths
    already in the processed list, and returns sorted Path objects.
    """
    processed_set = set(processed)
    found = []

    for scan_dir in scan_dirs:
        base = Path(scan_dir)
        if not base.is_dir():
            print(f"Warning: scan directory does not exist: {scan_dir}")
            continue
        pattern = str(base / '**' / 'sessions' / 'session_*.md')
        for match in globmod.glob(pattern, recursive=True):
            p = Path(match)
            posix = p.as_posix()
            if posix not in processed_set:
                found.append(p)

    # Sort by filename (stem) for chronological ordering
    found.sort(key=lambda p: p.name)
    return found


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='OpenCode Learning Aggregator'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--session', type=str,
                       help='Path to a single session log')
    group.add_argument('--scan', type=str, action='append',
                       metavar='DIR',
                       help='Scan directory for session_*.md files '
                            '(repeatable)')
    parser.add_argument('--bank', type=str, default='memory/bank.json',
                        help='Path to bank.json')
    parser.add_argument('--summary', type=str, default='memory/summary.json',
                        help='Path to summary.json')
    parser.add_argument('--auto-commit', action='store_true',
                        help='Auto-commit changes')
    parser.add_argument('--auto-push', action='store_true',
                        help='Auto-push after commit (requires --auto-commit)')
    args = parser.parse_args()

    # Require at least one mode
    if not args.session and not args.scan:
        parser.error('one of --session or --scan is required')

    bank_path = Path(args.bank)
    summary_path = Path(args.summary)
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

    # Load processed sessions tracking list
    processed = summary.get('processed_sessions', [])

    # Build list of session paths to process
    if args.session:
        # Single-session mode (existing behavior)
        sessions_to_process = [Path(args.session)]
        skipped_count = 0
    else:
        # Batch scan mode
        all_discovered = discover_sessions(args.scan, processed)
        sessions_to_process = all_discovered
        # Count how many were already processed (for reporting)
        total_in_dirs = []
        for scan_dir in args.scan:
            base = Path(scan_dir)
            if base.is_dir():
                pattern = str(base / '**' / 'sessions' / 'session_*.md')
                total_in_dirs.extend(globmod.glob(pattern, recursive=True))
        skipped_count = len(total_in_dirs) - len(sessions_to_process)

    if not sessions_to_process:
        print(f"No new sessions to process "
              f"(skipped {skipped_count} already-processed)")
        # Still save summary in case schema migrated
        save_json(summary_path, summary)
        return

    # Process each session
    total_added = 0
    total_reinforced = 0
    newly_processed_paths = []

    for session_path in sessions_to_process:
        print(f"Reading session: {session_path}")
        try:
            session_data = extract_session_data(session_path)
        except FileNotFoundError as e:
            print(f"  Skipping: {e}")
            continue

        new_heuristics = extract_heuristics_from_session(session_data)
        print(f"  Extracted {len(new_heuristics)} heuristic(s)")

        bank, added, reinforced = reinforce_or_append(bank, new_heuristics)
        total_added += added
        total_reinforced += reinforced
        print(f"  Added {added} new, reinforced {reinforced} existing")

        newly_processed_paths.append(session_path.as_posix())

    # Save bank once after all sessions processed
    save_json(bank_path, bank)

    # Update processed_sessions list
    processed.extend(newly_processed_paths)
    summary['processed_sessions'] = processed

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
    print(f"\nProcessed {len(newly_processed_paths)} new session(s), "
          f"skipped {skipped_count} already-processed")
    print(f"[OK] Bank: {len(bank)} entries "
          f"({total_added} new, {total_reinforced} reinforced)")
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
        session_path = (Path(args.session) if args.session
                        else sessions_to_process[0] if sessions_to_process
                        else None)
        repo_dir = (session_path.parent.parent
                    if session_path else Path.cwd())
        commit_session_log(session_path, bank_path, summary_path,
                           repo_dir, args.auto_push)


if __name__ == '__main__':
    main()
