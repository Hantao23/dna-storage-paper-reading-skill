#!/usr/bin/env python3
"""
Generate output templates from prompt templates.

Single source of truth: references/*.prompt.md
Generated files: assets/*.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TEMPLATE_PAIRS = (
    ("references/dna-short-template.prompt.md", "assets/dna-short-template.md"),
    ("references/dna-deep-template.prompt.md", "assets/dna-deep-template.md"),
)

COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.S)


def _extract_report_structure(prompt_text: str, source_path: Path) -> str:
    lines = prompt_text.splitlines()
    marker_index = next(
        (idx for idx, line in enumerate(lines) if "下面是结构参考" in line),
        None,
    )
    search_start = marker_index + 1 if marker_index is not None else 0

    for idx in range(search_start, len(lines)):
        line = lines[idx].strip()
        if line.startswith("# ") and "DNA 存储论文" in line and "<!--" not in line:
            return "\n".join(lines[idx:])

    raise ValueError(f"Cannot find report structure start in {source_path}")


def _normalize_output(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = COMMENT_RE.sub("", text)

    raw_lines = []
    for line in text.splitlines():
        line = line.rstrip()
        line = re.sub(r"([：:])\s*$", r"\1<复制原文>", line) if "证据原文摘录" in line and "<复制原文>" not in line else line
        raw_lines.append(line)

    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()

    clean_lines: list[str] = []
    last_blank = False
    for line in raw_lines:
        stripped = line.strip()
        if stripped in {"-", "*"}:
            continue
        is_blank = not line.strip()
        if is_blank and last_blank:
            continue
        clean_lines.append(line)
        last_blank = is_blank

    return "\n".join(clean_lines) + "\n"


def generate_from_prompt(source_path: Path) -> str:
    prompt_text = source_path.read_text(encoding="utf-8")
    structure = _extract_report_structure(prompt_text, source_path)
    return _normalize_output(structure)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync output templates from prompt templates."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether generated outputs are up to date.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    mismatches: list[str] = []
    updated: list[str] = []

    for source_rel, target_rel in TEMPLATE_PAIRS:
        source_path = root / source_rel
        target_path = root / target_rel

        generated = generate_from_prompt(source_path)
        current = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        if generated != current:
            if args.check:
                mismatches.append(f"{target_rel} (source: {source_rel})")
            else:
                target_path.write_text(generated, encoding="utf-8")
                updated.append(target_rel)

    if args.check:
        if mismatches:
            print("[FAIL] Output templates are out of date:")
            for item in mismatches:
                print(f"- {item}")
            print("Run: python scripts/sync_output_templates.py")
            return 2
        print("[OK] Output templates are in sync.")
        return 0

    if updated:
        print("Updated output templates:")
        for item in updated:
            print(f"- {item}")
    else:
        print("No changes. Output templates already in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
