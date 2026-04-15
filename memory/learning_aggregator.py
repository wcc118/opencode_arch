#!/usr/bin/env python3
"""
Learning Aggregator for OpenCode Continuous Learning System.
Extracts heuristics from session logs, appends to memory bank.

Usage:
    python learning_aggregator.py --session LOG_PATH
"""

import argparse
import json
import re
import os
from datetime import datetime
from pathlib import Path


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


def extract_session_data(session_path: Path) -> dict:
    """Extract key data from a session log."""
    if not session_path.exists():
        raise FileNotFoundError(f"Session log not found: {session_path}")
    
    content = session_path.read_text(encoding='utf-8')
    
    # Extract "What Worked" section
    worked_match = re.search(r'## What Worked\s*\n(.*?)(?=\n##|$)', content, re.DOTALL)
    worked = worked_match.group(1).strip() if worked_match else ""
    
    # Extract "What Failed" section
    failed_match = re.search(r'## What Failed\s*\n(.*?)(?=\n##|$)', content, re.DOTALL)
    failed = failed_match.group(1).strip() if failed_match else ""
    
    # Extract session ID from filename
    session_id = session_path.stem  # e.g., "session_20260415_000000" → "session_20260415_000000"
    
    return {
        'worked': worked,
        'failed': failed,
        'session_id': session_id
    }


def generate_heuristic(pattern: str, suggestion: str, heuristic_type: str, confidence: str = "medium") -> dict:
    """Generate a heuristic object. Compact keys for token efficiency."""
    return {
        "t": heuristic_type,
        "p": pattern,
        "s": suggestion,
        "c": confidence,
        "ts": datetime.utcnow().isoformat() + "Z",
        "sid": "placeholder_session_id"  # replaced during extraction
    }


def extract_heuristics_from_session(data: dict) -> list:
    """Extract heuristics from session worked/failed sections."""
    heuristics = []
    worked = data['worked']
    failed = data['failed']
    
    # Parse "What Worked" lines (each line = heuristic)
    for line in worked.split('\n'):
        line = line.strip()
        # Remove leading bullet points for pattern
        if line.startswith(('-', '*', '•', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
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
            confidence="high"
        ))
    
    # Parse "What Failed" lines (each line = anti-pattern)
    for line in failed.split('\n'):
        line = line.strip()
        # Remove leading bullet points for pattern
        if line.startswith(('-', '*', '•', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
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
            confidence="medium"
        ))
    
    # Replace placeholder session_id
    for h in heuristics:
        h['sid'] = data['session_id']
    
    return heuristics


def compress_heuristics(heuristics: list, max_heuristics: int = 3) -> list:
    """Compress heuristics list to fit in ≤300 tokens."""
    # Deduplicate by pattern+type first
    seen = set()
    deduped = []
    for h in heuristics:
        key = (h['p'], h['t'])
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    
    # Sort by confidence (high>medium>low) and age, keep top N
    sorted_h = sorted(deduped, key=lambda x: (
        {"high": 3, "medium": 2, "low": 1}.get(x.get('c', 'low'), 1),
        x.get('ts', '')
    ), reverse=True)
    return sorted_h[:max_heuristics]


def main():
    parser = argparse.ArgumentParser(description='OpenCode Learning Aggregator')
    parser.add_argument('--session', type=str, required=True, help='Path to session log')
    parser.add_argument('--bank', type=str, default='memory/bank.json', help='Path to bank.json')
    parser.add_argument('--summary', type=str, default='memory/summary.json', help='Path to summary.json')
    args = parser.parse_args()
    
    session_path = Path(args.session)
    bank_path = Path(args.bank)
    summary_path = Path(args.summary)
    
    # Load current state
    bank = load_json(bank_path)
    summary = load_json(summary_path)
    
    # Extract session data
    print(f"Reading session: {session_path}")
    session_data = extract_session_data(session_path)
    
    # Generate heuristics
    new_heuristics = extract_heuristics_from_session(session_data)
    print(f"Extracted {len(new_heuristics)} heuristics")
    
    # Deduplicate based on pattern + type + session_id (compact keys: p, t, sid)
    existing_hashes = {(h['p'], h['t'], h['sid']) for h in bank}
    unique_heuristics = [h for h in new_heuristics if (h['p'], h['t'], h['sid']) not in existing_hashes]
    
    # Append to bank
    bank.extend(unique_heuristics)
    save_json(bank_path, bank)
    print(f"Appended {len(unique_heuristics)} new heuristic(s) to {bank_path}")
    print(f"Appended to {bank_path}")
    
    # Update summary
    summary['last_updated'] = datetime.utcnow().isoformat() + "Z"
    summary['total_sessions'] = summary.get('total_sessions', 0) + 1
    # Compress heuristics for injection (≤300 tokens)
    compressed = compress_heuristics(bank, max_heuristics=5)
    summary['heuristics'] = compressed
    save_json(summary_path, summary)
    print(f"Updated {summary_path}")
    
    print(f"\n[OK] Added {len(new_heuristics)} heuristic(s) to bank")
    print(f"Summary updated: {summary['total_sessions']} session(s) logged")


if __name__ == '__main__':
    main()
