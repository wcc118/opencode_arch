#!/usr/bin/env python3
"""Count tokens in summary.json for startup injection budget validation."""
import json
from pathlib import Path


def estimate_tokens(data) -> int:
    """Estimate token count from JSON data. ~4 chars per token."""
    text = json.dumps(data, separators=(',', ':'))
    return len(text) // 4


if __name__ == '__main__':
    # Standalone usage: report on current summary.json
    script_dir = Path(__file__).parent.resolve()
    summary_path = script_dir / 'summary.json'

    with open(summary_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tokens = estimate_tokens(data)
    print(f"Compact JSON length: {len(json.dumps(data, separators=(',', ':')))} chars")
    print(f"Estimated tokens: {tokens}")

    if tokens <= 500:
        print(f"Status: WITHIN objective (<=500)")
    elif tokens <= 1000:
        print(f"Status: OVER objective, within threshold (<=1000)")
    else:
        print(f"Status: EXCEEDS hard threshold (>1000)!")

    print(f"\nSummary.json content:\n{json.dumps(data, indent=2)}")
