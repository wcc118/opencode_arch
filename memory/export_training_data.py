#!/usr/bin/env python3
"""Export training data from OpenCode learning system for model fine-tuning.

Reads bank.json (heuristics) and session logs to produce JSONL files
in formats suitable for fine-tuning language models.

Formats:
  - heuristic_pairs:     Teach the model to apply learned patterns
  - session_narratives:  Teach task execution flow from full session logs
  - corrective_pairs:    Teach self-correction from failure patterns
  - dpo_pairs:           Preference optimization from success/failure contrasts

Usage:
    python export_training_data.py \\
      --bank C:/Users/wcc11/.config/opencode/memory/bank.json \\
      --sessions-dir C:/Users/wcc11/.config/opencode/sessions \\
      --sessions-dir G:/Projects/CashFlow/sessions \\
      --output-dir C:/Users/wcc11/.config/opencode/memory/training \\
      --formats all

Requires: stdlib only (no pip dependencies).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_HEURISTIC = (
    "You are an AI coding assistant that learns from past experiences."
)
SYSTEM_NARRATIVE = (
    "You are an AI coding assistant. You track what works and what fails "
    "across sessions to continuously improve."
)
SYSTEM_CORRECTIVE = (
    "You are an AI coding assistant that learns from mistakes."
)

CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

ALL_FORMATS = [
    "heuristic_pairs",
    "session_narratives",
    "corrective_pairs",
    "dpo_pairs",
]


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

def load_json(path: Path) -> list:
    """Load bank.json, return empty list if missing."""
    if not path.exists():
        print(f"Warning: {path} not found, skipping.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_jsonl(path: Path, records: list) -> int:
    """Write a list of dicts as JSONL. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy topic matching (DPO pairing).

    Lowercases, strips backticks & parentheticals, collapses whitespace.
    """
    text = text.strip().lower()
    text = text.replace("`", "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def word_set(text: str) -> set:
    """Extract meaningful words (len >= 3) from normalized text."""
    return {w for w in normalize_for_matching(text).split() if len(w) >= 3}


def jaccard_similarity(a: set, b: set) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def reinforcement_note(rb: list) -> str:
    """Build reinforcement suffix from rb array."""
    if rb:
        return f", reinforced across {len(rb)} sessions"
    return ""


def confidence_at_least(entry: dict, min_conf: str) -> bool:
    """Check if entry confidence meets minimum threshold."""
    return CONFIDENCE_ORDER.get(entry.get("c", "low"), 0) >= CONFIDENCE_ORDER.get(min_conf, 0)


# ---------------------------------------------------------------------------
# Format 1: Heuristic Pairs
# ---------------------------------------------------------------------------

def build_heuristic_pairs(bank: list, min_confidence: str) -> list:
    """Build chat-format training examples from bank.json heuristics.

    Success heuristics become "what should I do?" examples.
    Failure heuristics become "what pitfalls?" examples.
    """
    records = []

    for entry in bank:
        if not confidence_at_least(entry, min_confidence):
            continue

        h_type = entry.get("t", "success")
        pattern = entry.get("p", "")
        suggestion = entry.get("s", "")
        confidence = entry.get("c", "medium")
        sid = entry.get("sid", "unknown")
        rb = entry.get("rb", [])

        if not pattern or not suggestion:
            continue

        rb_note = reinforcement_note(rb)

        if h_type == "success":
            user_msg = (
                f"I'm working on a task that involves: {pattern}. "
                f"Based on past experience, what should I do?"
            )
            assistant_msg = (
                f"Based on experience from session {sid}: {suggestion}. "
                f"This pattern has been confirmed {confidence} confidence"
                f"{rb_note}."
            )
        else:
            user_msg = (
                f"I'm working on a task that involves: {pattern}. "
                f"What pitfalls should I watch out for?"
            )
            assistant_msg = (
                f"Based on experience from session {sid}: {suggestion}. "
                f"This was identified as a {confidence}-confidence "
                f"anti-pattern{rb_note}."
            )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_HEURISTIC},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ]
        })

    return records


# ---------------------------------------------------------------------------
# Format 2: Session Narratives
# ---------------------------------------------------------------------------

def parse_session_sections(content: str) -> dict:
    """Parse a session log into its markdown sections.

    Returns dict with keys: worked, failed, decisions, done, open_items.
    """
    sections = {
        "worked": "",
        "failed": "",
        "decisions": "",
        "done": "",
        "open_items": "",
    }

    # Combined format: "## What Worked / What Failed" with ### sub-headers
    combined_match = re.search(
        r"## What Worked\s*/\s*What Failed\s*\n(.*?)(?=\n## |\Z)",
        content, re.DOTALL,
    )
    if combined_match:
        block = combined_match.group(1)
        lines = block.split("\n")
        state = "worked"
        worked_lines, failed_lines = [], []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^###\s+What Worked", stripped, re.IGNORECASE):
                state = "worked"
                continue
            if re.match(r"^###\s+What Failed", stripped, re.IGNORECASE):
                state = "failed"
                continue
            if stripped.startswith("#"):
                continue
            if stripped:
                (worked_lines if state == "worked" else failed_lines).append(stripped)
        sections["worked"] = "\n".join(worked_lines)
        sections["failed"] = "\n".join(failed_lines)
    else:
        # Separate sections
        for key, heading in [
            ("worked", r"## What Worked"),
            ("failed", r"## What Failed"),
        ]:
            m = re.search(
                rf"{heading}\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
            )
            if m:
                sections[key] = m.group(1).strip()

    # Other sections
    for key, heading in [
        ("decisions", r"## Decisions"),
        ("done", r"## Done"),
        ("open_items", r"## Open Items"),
    ]:
        m = re.search(
            rf"{heading}[^\n]*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
        )
        if m:
            sections[key] = m.group(1).strip()

    return sections


def build_session_narratives(session_dirs: list) -> list:
    """Build chat-format training examples from raw session logs.

    Each session becomes a "extract key lessons" example.
    """
    records = []
    session_files = _discover_session_files(session_dirs)

    for path in session_files:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Warning: Could not read {path}: {e}")
            continue

        session_id = path.stem
        sections = parse_session_sections(content)

        # Build the assistant's structured response
        worked_items = sections["worked"] or "No explicit successes recorded."
        failed_items = sections["failed"] or "No explicit failures recorded."

        # Build heuristic summary from both sections
        heuristic_lines = []
        for line in (sections["worked"] or "").split("\n"):
            line = _strip_bullet(line)
            if line:
                heuristic_lines.append(f"- DO: {line}")
        for line in (sections["failed"] or "").split("\n"):
            line = _strip_bullet(line)
            if line:
                heuristic_lines.append(f"- AVOID: {line}")
        heuristic_summary = (
            "\n".join(heuristic_lines) if heuristic_lines
            else "No actionable heuristics extracted."
        )

        user_msg = (
            "Here is a session log from a previous coding session. "
            f"Extract the key lessons:\n\n{content}"
        )
        assistant_msg = (
            f"## Key Lessons from {session_id}\n\n"
            f"### What Worked\n{worked_items}\n\n"
            f"### What Failed\n{failed_items}\n\n"
            f"### Actionable Heuristics\n{heuristic_summary}"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_NARRATIVE},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ]
        })

    return records


# ---------------------------------------------------------------------------
# Format 3: Corrective Pairs
# ---------------------------------------------------------------------------

def build_corrective_pairs(bank: list, min_confidence: str) -> list:
    """Build self-correction training examples from failure heuristics.

    Teaches the model to respond to "this went wrong" with a corrective plan.
    """
    records = []

    for entry in bank:
        if entry.get("t") != "failure":
            continue
        if not confidence_at_least(entry, min_confidence):
            continue

        pattern = entry.get("p", "")
        suggestion = entry.get("s", "")
        if not pattern or not suggestion:
            continue

        # Build a richer corrective suggestion from the failure data
        corrective = suggestion
        rb = entry.get("rb", [])
        if rb:
            corrective += (
                f" This anti-pattern has been observed across "
                f"{len(rb) + 1} sessions — it is a recurring issue. "
                f"Proactively guard against it."
            )
        else:
            corrective += (
                " Watch for this pattern and address it early "
                "before it compounds."
            )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_CORRECTIVE},
                {
                    "role": "user",
                    "content": (
                        f"In a previous session, this went wrong: {pattern}. "
                        f"How should I handle this differently next time?"
                    ),
                },
                {"role": "assistant", "content": corrective},
            ]
        })

    return records


# ---------------------------------------------------------------------------
# Format 4: DPO Pairs
# ---------------------------------------------------------------------------

def build_dpo_pairs(
    bank: list, min_confidence: str, similarity_threshold: float = 0.3
) -> list:
    """Build DPO (Direct Preference Optimization) pairs.

    Pairs success and failure heuristics that address the same topic area,
    matched by Jaccard similarity on normalized word sets.

    Each pair provides a 'chosen' (success approach) and 'rejected'
    (failure approach) for the same task context.
    """
    successes = []
    failures = []

    for entry in bank:
        if not confidence_at_least(entry, min_confidence):
            continue
        pattern = entry.get("p", "")
        suggestion = entry.get("s", "")
        if not pattern or not suggestion:
            continue

        words = word_set(pattern + " " + suggestion)
        item = {"entry": entry, "words": words}

        if entry.get("t") == "success":
            successes.append(item)
        elif entry.get("t") == "failure":
            failures.append(item)

    records = []
    used_failures = set()  # index of failures already paired

    for si in successes:
        best_score = 0.0
        best_fi = -1

        for fi, fail in enumerate(failures):
            if fi in used_failures:
                continue
            score = jaccard_similarity(si["words"], fail["words"])
            if score > best_score:
                best_score = score
                best_fi = fi

        if best_score >= similarity_threshold and best_fi >= 0:
            used_failures.add(best_fi)
            s_entry = si["entry"]
            f_entry = failures[best_fi]["entry"]

            # Build a shared task context from overlapping words
            overlap = si["words"] & failures[best_fi]["words"]
            task_context = (
                " ".join(sorted(overlap)) if overlap
                else normalize_for_matching(s_entry["p"])
            )

            records.append({
                "prompt": f"I need to {task_context}",
                "chosen": s_entry.get("s", ""),
                "rejected": f_entry.get("s", ""),
            })

    return records


# ---------------------------------------------------------------------------
# Session file discovery
# ---------------------------------------------------------------------------

def _discover_session_files(session_dirs: list) -> list:
    """Find all session_*.md files in the given directories.

    Searches both the directory itself and a sessions/ subdirectory.
    """
    found = []
    seen = set()

    for dir_str in session_dirs:
        base = Path(dir_str)
        if not base.is_dir():
            print(f"Warning: sessions directory does not exist: {dir_str}")
            continue

        # Check both the dir itself and any sessions/ subdirectory
        search_dirs = [base]
        sessions_sub = base / "sessions"
        if sessions_sub.is_dir():
            search_dirs.append(sessions_sub)

        for sdir in search_dirs:
            for f in sorted(sdir.glob("session_*.md")):
                key = str(f.resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(f)

    found.sort(key=lambda p: p.name)
    return found


def _strip_bullet(line: str) -> str:
    """Strip leading bullet/number from a line."""
    line = line.strip()
    if not line:
        return ""
    if line[0] in "-*\u2022":
        line = line[1:].strip()
    elif re.match(r"^\d+\.\s", line):
        line = re.sub(r"^\d+\.\s*", "", line)
    return line


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--bank",
        type=str,
        required=True,
        help="Path to bank.json (required)",
    )
    parser.add_argument(
        "--sessions-dir",
        type=str,
        action="append",
        default=[],
        dest="sessions_dirs",
        help="Path(s) to session log directories (can be specified multiple times)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Where to write JSONL files (default: training/ relative to bank)",
    )
    parser.add_argument(
        "--formats",
        type=str,
        default="all",
        help=(
            "Comma-separated list of formats to generate: "
            "heuristic_pairs,session_narratives,corrective_pairs,dpo_pairs,all "
            "(default: all)"
        ),
    )
    parser.add_argument(
        "--min-confidence",
        type=str,
        default="low",
        choices=["low", "medium", "high"],
        help="Minimum confidence to include (default: low — include everything)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    bank_path = Path(args.bank)
    output_dir = (
        Path(args.output_dir) if args.output_dir
        else bank_path.parent / "training"
    )

    # Parse requested formats
    if args.formats.strip().lower() == "all":
        formats = set(ALL_FORMATS)
    else:
        formats = {f.strip() for f in args.formats.split(",") if f.strip()}
        invalid = formats - set(ALL_FORMATS)
        if invalid:
            print(f"Error: Unknown format(s): {', '.join(sorted(invalid))}")
            print(f"Valid formats: {', '.join(ALL_FORMATS)}")
            sys.exit(1)

    # Load bank
    bank = load_json(bank_path)
    if not bank:
        print(f"Warning: bank.json at {bank_path} is empty or missing.")

    # Ensure output dir exists
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {}

    # Format 1: Heuristic Pairs
    if "heuristic_pairs" in formats:
        records = build_heuristic_pairs(bank, args.min_confidence)
        out_path = output_dir / "heuristic_pairs.jsonl"
        count = write_jsonl(out_path, records)
        stats["heuristic_pairs"] = count
        print(f"  heuristic_pairs:     {count:>4} examples -> {out_path}")

    # Format 2: Session Narratives
    if "session_narratives" in formats:
        if args.sessions_dirs:
            records = build_session_narratives(args.sessions_dirs)
        else:
            print("  session_narratives:  skipped (no --sessions-dir provided)")
            records = []
        out_path = output_dir / "session_narratives.jsonl"
        count = write_jsonl(out_path, records)
        stats["session_narratives"] = count
        print(f"  session_narratives:  {count:>4} examples -> {out_path}")

    # Format 3: Corrective Pairs
    if "corrective_pairs" in formats:
        records = build_corrective_pairs(bank, args.min_confidence)
        out_path = output_dir / "corrective_pairs.jsonl"
        count = write_jsonl(out_path, records)
        stats["corrective_pairs"] = count
        print(f"  corrective_pairs:    {count:>4} examples -> {out_path}")

    # Format 4: DPO Pairs
    if "dpo_pairs" in formats:
        records = build_dpo_pairs(bank, args.min_confidence)
        out_path = output_dir / "dpo_pairs.jsonl"
        count = write_jsonl(out_path, records)
        stats["dpo_pairs"] = count
        print(f"  dpo_pairs:           {count:>4} examples -> {out_path}")

    # Summary
    total = sum(stats.values())
    parts = [f"{stats.get(f, 0)} {f.replace('_', ' ')}" for f in ALL_FORMATS if f in stats]
    print(f"\nGenerated {', '.join(parts)}")
    print(f"Total: {total} training examples in {output_dir}")

    if total == 0:
        print(
            "\nNo training data generated. Check that bank.json has entries "
            "and/or session logs exist in the provided directories."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
