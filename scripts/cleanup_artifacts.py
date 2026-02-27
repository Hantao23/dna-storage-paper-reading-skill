#!/usr/bin/env python3
"""
Cleanup utility for paper-reading extraction artifacts.

Supports:
- bundle layout: <target>/<prefix>/
- flat legacy layout: <target>/<prefix>_*.{txt,json,md} and <target>/<prefix>_images/
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import List, Optional, Set


LEGACY_SUFFIX_RE = re.compile(
    r"^(?P<prefix>.+)_(?:fulltext\.txt|metadata\.json|urls_all\.txt|url_hits\.json|"
    r"resource_links(?:_priority)?\.json|figure_captions\.json|table_captions\.json|"
    r"code_signals\.json|availability_snippets\.json|tables\.json|images_manifest\.json|"
    r"image_gallery\.md)$"
)
LEGACY_IMAGE_DIR_RE = re.compile(r"^(?P<prefix>.+)_images$")
MD_IMAGE_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")


def detect_flat_prefixes(target_dir: Path) -> List[str]:
    prefixes: Set[str] = set()
    for item in target_dir.iterdir():
        if item.is_file():
            m = LEGACY_SUFFIX_RE.match(item.name)
            if m:
                prefixes.add(m.group("prefix"))
        elif item.is_dir():
            m = LEGACY_IMAGE_DIR_RE.match(item.name)
            if m:
                prefixes.add(m.group("prefix"))
    return sorted(prefixes)


def collect_paths_for_prefix(target_dir: Path, prefix: str) -> List[Path]:
    candidates: List[Path] = []
    bundle_dir = target_dir / prefix
    if bundle_dir.exists() and bundle_dir.is_dir():
        candidates.append(bundle_dir)

    for item in target_dir.glob(f"{prefix}_*"):
        if item.exists():
            candidates.append(item)
    return sorted(set(candidates))


def remove_path(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def strip_image_links_in_report(report_path: Path, dry_run: bool) -> None:
    lines = report_path.read_text(encoding="utf-8").splitlines()
    cleaned = [ln for ln in lines if not MD_IMAGE_LINE_RE.match(ln)]
    if dry_run:
        return
    report_path.write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")


def resolve_final_report_path(target_dir: Path, report_name: str) -> Path:
    report_raw = str(report_name or "").strip()
    if report_raw and report_raw.lower() != "auto":
        return (target_dir / report_raw).resolve()

    metadata_path = target_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
        summary_raw = str(metadata.get("summary_file", "")).strip()
        if summary_raw:
            summary_path = Path(summary_raw).expanduser().resolve()
            try:
                summary_path.relative_to(target_dir.resolve())
            except Exception:
                pass
            else:
                return summary_path

    candidates = sorted(target_dir.glob("*阅读总结.md"))
    if len(candidates) == 1:
        return candidates[0].resolve()
    if not candidates:
        raise SystemExit(
            "[ERROR] could not auto-detect report. Pass --report-name <report.md> or keep metadata.json."
        )
    raise SystemExit(
        f"[ERROR] multiple report candidates found ({len(candidates)}). Pass --report-name explicitly."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup paper-reading artifacts.")
    parser.add_argument("--target-dir", required=True, help="Artifact directory to clean.")
    parser.add_argument(
        "--delete-prefix",
        action="append",
        default=[],
        help="Prefix to delete. Repeatable.",
    )
    parser.add_argument(
        "--auto-delete-flat",
        action="store_true",
        help="Delete all detected legacy flat-layout prefixes.",
    )
    parser.add_argument(
        "--keep-prefix",
        action="append",
        default=[],
        help="Prefix to keep even if selected for deletion. Repeatable.",
    )
    parser.add_argument(
        "--final-md-only",
        action="store_true",
        help="In a bundle directory, keep only the final markdown report and delete all other files.",
    )
    parser.add_argument(
        "--report-name",
        default="auto",
        help="Report filename used with --final-md-only. Use 'auto' to read metadata.json/auto-detect (default: auto).",
    )
    parser.add_argument(
        "--keep-file",
        action="append",
        default=[],
        help="With --final-md-only, keep extra files/dirs under target-dir (relative paths). Repeatable.",
    )
    parser.add_argument(
        "--drop-images-dir",
        action="store_true",
        help="With --final-md-only, also delete images/ directory.",
    )
    parser.add_argument(
        "--strip-image-links",
        action="store_true",
        help="With --final-md-only, remove markdown image lines from final report.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned deletions only.")
    args = parser.parse_args()

    target_dir = Path(args.target_dir).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        raise SystemExit(f"[ERROR] target directory not found: {target_dir}")

    if args.final_md_only:
        report_path = resolve_final_report_path(target_dir=target_dir, report_name=str(args.report_name))
        if not report_path.exists():
            raise SystemExit(f"[ERROR] report not found: {report_path}")

        keep_paths = {report_path.resolve()}
        images_dir = target_dir / "images"
        if images_dir.exists() and images_dir.is_dir() and not args.drop_images_dir:
            keep_paths.add(images_dir.resolve())

        for raw_keep in args.keep_file:
            keep_rel = str(raw_keep).strip()
            if not keep_rel:
                continue
            keep_path = (target_dir / keep_rel).resolve()
            try:
                keep_path.relative_to(target_dir.resolve())
            except Exception:
                raise SystemExit(f"[ERROR] --keep-file must be under target-dir: {keep_rel}")
            if keep_path.exists():
                keep_paths.add(keep_path)

        to_delete = [p for p in target_dir.iterdir() if p.resolve() not in keep_paths]
        print(f"target_dir={target_dir}")
        print(f"dry_run={args.dry_run}")
        print("mode=final-md-only")
        print(f"report={report_path}")
        print(f"drop_images_dir={args.drop_images_dir}")
        if args.keep_file:
            print(f"keep_file={args.keep_file}")
        print(f"strip_image_links={args.strip_image_links}")
        print(f"paths_to_delete={len(to_delete)}")
        for path in sorted(to_delete):
            print(f"- {path}")
            remove_path(path, args.dry_run)

        if args.strip_image_links:
            print(f"strip_image_links_from={report_path}")
            strip_image_links_in_report(report_path, args.dry_run)

        if args.dry_run:
            print("[OK] dry-run complete.")
        else:
            print("[OK] final-md-only cleanup complete.")
        return 0

    delete_prefixes: Set[str] = {p.strip() for p in args.delete_prefix if p.strip()}
    if args.auto_delete_flat:
        delete_prefixes.update(detect_flat_prefixes(target_dir))

    keep_prefixes: Set[str] = {p.strip() for p in args.keep_prefix if p.strip()}
    delete_prefixes -= keep_prefixes

    if not delete_prefixes:
        print("[INFO] nothing to delete.")
        return 0

    to_delete: List[Path] = []
    for prefix in sorted(delete_prefixes):
        to_delete.extend(collect_paths_for_prefix(target_dir, prefix))

    # Keep only unique paths.
    unique_paths = sorted(set(to_delete))
    if not unique_paths:
        print("[INFO] no matching artifact paths found.")
        return 0

    print(f"target_dir={target_dir}")
    print(f"dry_run={args.dry_run}")
    print(f"delete_prefixes={sorted(delete_prefixes)}")
    print(f"paths_to_delete={len(unique_paths)}")
    for path in unique_paths:
        print(f"- {path}")
        remove_path(path, args.dry_run)

    if args.dry_run:
        print("[OK] dry-run complete.")
    else:
        print("[OK] cleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
