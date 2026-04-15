#!/usr/bin/env python3
"""Count tokens in summary.json for startup injection."""
import json
from pathlib import Path

# Get script directory and resolve absolute path
script_dir = Path(__file__).parent.resolve()
summary_path = script_dir / 'summary.json'

# Quick estimate: 1 token ≈ 4 characters for English text
with open(summary_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

text = json.dumps(data, separators=(',', ':'))
print(f"Compact JSON length: {len(text)} chars")
print(f"Estimated tokens: {len(text) // 4}")
print(f"\nSummary.json content:\n{json.dumps(data, indent=2)}")
