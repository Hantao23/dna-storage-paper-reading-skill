#!/usr/bin/env python3
"""
Write final markdown report to the summary_file declared in metadata.json.

Usage examples:
  python scripts/write_final_report.py --artifact-dir /path/to/paper_dir --from-stdin
  python scripts/write_final_report.py --artifact-dir /path/to/paper_dir --input-file /path/to/final.md
"""

import argparse
import json
import sys
from pathlib import Path


def load_summary_path(artifact_dir: Path) -> Path:
    metadata_path = artifact_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"[ERROR] metadata.json not found: {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    summary_raw = str(metadata.get("summary_file", "")).strip()
    if summary_raw:
        return Path(summary_raw).expanduser().resolve()

    fallback = artifact_dir / f"{artifact_dir.name}阅读总结.md"
    return fallback.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write final report markdown to summary_file.")
    parser.add_argument("--artifact-dir", required=True, help="Paper artifact directory containing metadata.json.")
    parser.add_argument("--input-file", help="Markdown file to write as final report.")
    parser.add_argument("--from-stdin", action="store_true", help="Read markdown content from stdin.")
    args = parser.parse_args()

    if bool(args.input_file) == bool(args.from_stdin):
        raise SystemExit("[ERROR] specify exactly one of --input-file or --from-stdin")

    artifact_dir = Path(args.artifact_dir).expanduser().resolve()
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise SystemExit(f"[ERROR] artifact_dir not found: {artifact_dir}")

    if args.from_stdin:
        content = sys.stdin.read()
    else:
        input_path = Path(str(args.input_file)).expanduser().resolve()
        if not input_path.exists():
            raise SystemExit(f"[ERROR] input file not found: {input_path}")
        content = input_path.read_text(encoding="utf-8")

    if not content.strip():
        raise SystemExit("[ERROR] report content is empty.")

    summary_path = load_summary_path(artifact_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    print(f"artifact_dir={artifact_dir}")
    print(f"summary_file={summary_path}")
    print(f"chars={len(content)}")
    print("[OK] final report written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
