#!/usr/bin/env python3
"""
Fail if the summary report looks like an unfilled template.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Optional, Tuple


PLACEHOLDER_TOKENS = [
    "DNA 存储论文精读模板",
    "DNA 存储论文略读模板",
    "[明确|推断|缺失]",
    "<选一：[明确]/[推断]/[缺失]>",
    "<选一：[原文支持]/[原文推理得到]/[原文未给或未找到]>",
    "<填写该节的一条判断/结论>",
    "<图/表支持的判断或结论>",
    "<复制原文>",
    "证据原文摘录：<复制原文>",
    "images/your-figure.png",
    "下面是结构参考（带提示词标注）",
    "<!-- HINT:",
]

DISALLOWED_PHRASES = [
    "面向 DNA 存储领域“实验主导型论文”的结构化精读笔记",
    "【论述",
    "[原文支持]",
    "[原文推理得到]",
    "[原文未给或未找到]",
    "写作约束（必填）",
    "请用 1-2 段",
    "证据原文摘录（直接复制原文）",
    "写作提示（不写入最终报告）",
    "写作须知（必读，不写入最终报告）",
    "最终报告不要复制",
    "如果论文中没有模板中的需求和要点的可以不写",
    "见下",
    "原文为表格，非图片",
    "本 bundle 未渲染",
    "本bundle未渲染",
]

LEGACY_JUDGMENT_TAGS = ["[明确]", "[推断]", "[缺失]"]

BLANK_FIELD_RE = re.compile(r"^\s*-\s*[^:：]{1,40}[：:]\s*$")
BLANK_NUMBERED_FIELD_RE = re.compile(r"^\s*\d+\.\s*[^:：]{1,60}[：:]\s*$")
BLANK_CLAIM_RE = re.compile(r"^\s*>\s*论述\d*[：:]\s*$")
LEVEL2_HEADING_RE = re.compile(r"^\s*##\s+[^#].*$")
LEVEL3_FOOTNOTE_HEADING_RE = re.compile(r"^\s*###\s+证据脚注\s*$")
LEVEL2_FOOTNOTE_SECTION_RE = re.compile(r"^\s*##\s+[0-9]+\s+证据脚注\s*$")
LEVEL2_FIGURE_SECTION_RE = re.compile(r"^\s*##\s+9\s+图表逐条解读\s*$")
FIGURE_LIST_HEADING_RE = re.compile(r"^\s*###\s+9\.1\s+图表清单\s*$")
FIGURE_NUMBERED_FIELD_RE = re.compile(r"^\s*\d+\.\s*图/表编号\s*[：:]\s*")
FOOTNOTE_REF_RE = re.compile(r"\[\^([0-9]+-[0-9]+)\]")
FOOTNOTE_DOT_STYLE_RE = re.compile(r"\[\^[0-9]+\.[0-9]+\]")
FOOTNOTE_DEF_LINE_RE = re.compile(r"^\s*\[\^([0-9]+-[0-9]+)\]:\s*(.*)$")
MULTISPACE_RE = re.compile(r"\s+")
INLINE_CODE_IMAGE_RE = re.compile(r"`!\[[^\]]*\]\([^)]+\)`")
QUOTED_IMAGE_URL_RE = re.compile(r"!\[[^\]]*\]\(\s*[\"'“”‘’]")
QUOTED_IMAGE_WRAPPER_RE = re.compile(r"[“”‘’']!\[[^\]]*\]\([^)]+\)[“”‘’']")
BODY_MISSING_WORDING_RE = re.compile(r"(不适用|原文未描述|原文未给|原文未找到|原文缺失)")
OTHER_NOT_INVOLVED_RE = re.compile(r"其它\s*[:：]\s*本文不涉及")
SECTION12_HEADING_RE = re.compile(r"^\s*##\s+12\s+结论、证据与缺点\s*$")
LLM_REFLECTION_HEADING_RE = re.compile(r"^\s*##\s+14\s+复盘评分与发表定位\s*$")
CONCLUSION_BULLET_RE = re.compile(r"^\s*-\s*结论\s*([A-Za-z0-9]+)(?:（[^）]*）)?\s*[：:]\s*(.*)$")
SCORE_BULLET_RE = re.compile(
    r"^\s*-\s*(创新性|叙事性|复现性)(?:\s*[(（]\s*0\s*-\s*10(?:[^)）]*)[)）])?\s*[：:]\s*(.*)$"
)
FOOTNOTE_REF_CH12_RE = re.compile(r"\[\^12-\d+\]")
FOOTNOTE_REF_CH14_RE = re.compile(r"\[\^14-\d+\]")
PUBLISHED_VENUE_BULLET_RE = re.compile(r"^\s*-\s*论文实际发表\s*[：:]\s*(.*)$")
VENUE_TIER_BULLET_RE = re.compile(
    r"^\s*-\s*发表\s*(?:venue\s*)?(?:(?:期刊|会议)\s*)?档位判断(?:\s*[(（][^)）]*[)）])?\s*[：:]\s*(.*)$"
)
VENUE_FIT_BULLET_RE = re.compile(
    r"^\s*-\s*为什么能发表在该\s*(?:venue\s*)?(?:(?:期刊|会议)(?:\s*/\s*(?:期刊|会议))?\s*)?(?:\s*[(（][^)）]*[)）])?\s*[：:]\s*(.*)$"
)
PUBLISHABILITY_BULLET_RE = re.compile(r"^\s*-\s*可发表性推演(?:\s*[(（][^)）]*[)）])?\s*[：:]\s*(.*)$")
PUB_TIER_BULLET_RE = re.compile(
    r"^\s*-\s*可发表性(?:推演)?\s*[-—]?\s*(?:[(（]\s*)?(顶级|中等|一般)\s*(?:期刊/会议|期刊|会议)?(?:\s*[)）])?\s*[：:]\s*(.*)$"
)
PREPRINT_MARKERS = ("预印本", "arxiv", "biorxiv", "medrxiv", "preprint")


def load_metadata(artifact_dir: Path) -> dict:
    metadata_path = artifact_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"[ERROR] metadata.json not found: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def load_summary_path(metadata: dict, artifact_dir: Path) -> Path:
    summary_raw = str(metadata.get("summary_file", "")).strip()
    if summary_raw:
        return Path(summary_raw).expanduser().resolve()
    return (artifact_dir / f"{artifact_dir.name}阅读总结.md").resolve()


def normalize_summary_mode(raw: str) -> str:
    mode = str(raw).strip().lower()
    if mode in {"short", "略读", "lue-du", "skim"}:
        return "略读"
    return "精读"


def normalize_heading(line: str) -> str:
    return MULTISPACE_RE.sub(" ", line.strip())


def extract_level2_headings(text: str) -> list:
    headings = []
    for line in text.splitlines():
        if LEVEL2_HEADING_RE.match(line):
            headings.append(normalize_heading(line))
    return headings


def load_template_headings(summary_mode: str) -> tuple:
    root = Path(__file__).resolve().parents[1]
    template_name = "dna-short-template.md" if summary_mode == "略读" else "dna-deep-template.md"
    template_path = root / "assets" / template_name
    if not template_path.exists():
        raise SystemExit(f"[ERROR] template not found for heading check: {template_path}")
    headings = extract_level2_headings(template_path.read_text(encoding="utf-8"))
    if not headings:
        raise SystemExit(f"[ERROR] no level-2 headings found in template: {template_path}")
    return template_path, headings


def footnote_sort_key(note_id: str) -> tuple:
    chapter, index = note_id.split("-", 1)
    return int(chapter), int(index)


def extract_footnote_refs(text: str) -> set:
    return {m.group(1) for m in FOOTNOTE_REF_RE.finditer(text)}


def parse_footnote_blocks(text: str) -> dict:
    blocks = {}
    current_id = None

    for line in text.splitlines():
        match = FOOTNOTE_DEF_LINE_RE.match(line)
        if match:
            current_id = match.group(1)
            blocks[current_id] = [match.group(2).strip()]
            continue

        if current_id and (line.startswith("    ") or line.startswith("\t")):
            blocks[current_id].append(line.strip())
            continue

        current_id = None

    return {note_id: " ".join(parts).strip() for note_id, parts in blocks.items()}


def format_list(items: list, limit: int = 8) -> str:
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f", ... (+{len(items) - limit})"


def check_section_heading_integrity(report_text: str, expected: list) -> list:
    issues = []
    actual = extract_level2_headings(report_text)

    unexpected = [item for item in actual if item not in expected]

    if unexpected:
        issues.append(f"contains unexpected section headings: {format_list(unexpected)}")

    # Allow omitting entire level-2 sections when not applicable, but keep order.
    pos = 0
    for heading in expected:
        if pos < len(actual) and actual[pos] == heading:
            pos += 1
    if pos != len(actual):
        issues.append("section heading order does not follow template")

    return issues

def check_footnote_section_placement(report_text: str) -> list:
    issues = []
    lines = report_text.splitlines()
    level2_idx = [idx for idx, line in enumerate(lines) if LEVEL2_HEADING_RE.match(line)]

    if any(LEVEL3_FOOTNOTE_HEADING_RE.match(line) for line in lines):
        issues.append("contains per-section footnote heading `### 证据脚注`; footnotes must be unified at document end")

    footnote_sections = [idx for idx, line in enumerate(lines) if LEVEL2_FOOTNOTE_SECTION_RE.match(line)]
    if not footnote_sections:
        issues.append("missing final footnote section heading like `## N 证据脚注` (must be the last level-2 section)")
        return issues
    if len(footnote_sections) > 1:
        issues.append("contains multiple `## N 证据脚注` sections; keep exactly one at the end")
        return issues

    footnote_idx = footnote_sections[0]
    if level2_idx and level2_idx[-1] != footnote_idx:
        issues.append("footnote section must be the last level-2 section in the report")

    defs_before = [m.group(1) for idx, line in enumerate(lines[: footnote_idx + 1]) if (m := FOOTNOTE_DEF_LINE_RE.match(line))]
    if defs_before:
        issues.append(f"footnote definitions must appear after the final footnote section; found before: {format_list(sorted(set(defs_before), key=footnote_sort_key))}")

    defs_after = [m.group(1) for line in lines[footnote_idx + 1 :] if (m := FOOTNOTE_DEF_LINE_RE.match(line))]
    if not defs_after:
        issues.append("final footnote section exists but contains no footnote definitions")

    return issues


def check_figure_section_format(report_text: str) -> list:
    issues = []
    lines = report_text.splitlines()

    start_idx = next((idx for idx, line in enumerate(lines) if LEVEL2_FIGURE_SECTION_RE.match(line)), None)
    if start_idx is None:
        return issues

    end_idx = next((idx for idx in range(start_idx + 1, len(lines)) if LEVEL2_HEADING_RE.match(lines[idx])), len(lines))
    block = lines[start_idx:end_idx]

    if any(FIGURE_LIST_HEADING_RE.match(line) for line in block):
        issues.append("section 9 contains legacy subheading `### 9.1 图表清单`; remove it and use per-figure `###` headings")

    if any(FIGURE_NUMBERED_FIELD_RE.match(line) for line in block):
        issues.append("section 9 uses numbered '图/表编号' fields; use one `###` heading per figure/table instead")

    has_level3 = any(line.lstrip().startswith("### ") and not FIGURE_LIST_HEADING_RE.match(line) for line in block)
    if not has_level3:
        issues.append("section 9 must include per-figure/table level-3 headings (e.g. `### Figure 1 ...`)")

    return issues


def check_footnote_integrity(report_text: str) -> list:
    issues = []

    if FOOTNOTE_DOT_STYLE_RE.search(report_text):
        issues.append("contains dot-style footnote id; use [^章节-序号] such as [^1-1]")

    refs = extract_footnote_refs(report_text)
    footnote_blocks = parse_footnote_blocks(report_text)
    defs = set(footnote_blocks.keys())

    if not refs:
        issues.append("missing evidence footnote references like [^1-1]")
    if not defs:
        issues.append("missing evidence footnote definitions like [^1-1]: ...")

    missing_defs = sorted(refs - defs, key=footnote_sort_key)
    if missing_defs:
        issues.append(f"missing footnote definitions for refs: {format_list(missing_defs)}")

    missing_triplet = sorted(
        [
            note_id
            for note_id, content in footnote_blocks.items()
            if ("证据等级" not in content or "证据原文摘录" not in content or "来源位置" not in content)
        ],
        key=footnote_sort_key,
    )
    if missing_triplet:
        issues.append(f"footnote definitions missing evidence triplet fields: {format_list(missing_triplet)}")

    return issues


def check_markdown_media_syntax(report_text: str) -> list:
    issues = []
    if INLINE_CODE_IMAGE_RE.search(report_text):
        issues.append("contains inline-code image markdown like `![...](...)`; remove backticks so images render")
    if QUOTED_IMAGE_URL_RE.search(report_text):
        issues.append("contains quoted image URLs like ![...](\"images/...\"); remove quotes around paths")
    if QUOTED_IMAGE_WRAPPER_RE.search(report_text):
        issues.append("contains quoted image markdown like ‘![...](...)’; remove surrounding quotes so images render")
    return issues


def check_missing_wording(report_text: str) -> list:
    lines = report_text.splitlines()
    footnote_sections = [idx for idx, line in enumerate(lines) if LEVEL2_FOOTNOTE_SECTION_RE.match(line)]
    body = "\n".join(lines[: footnote_sections[0]]) if footnote_sections else report_text
    if BODY_MISSING_WORDING_RE.search(body):
        return ["uses legacy missing wording (e.g. 不适用/原文未描述/原文未给); use `本文不涉及` instead"]
    return []


def find_level2_section(lines: list[str], heading_re: re.Pattern) -> Optional[Tuple[int, int]]:
    start_idx = next((idx for idx, line in enumerate(lines) if heading_re.match(line)), None)
    if start_idx is None:
        return None
    end_idx = next(
        (idx for idx in range(start_idx + 1, len(lines)) if LEVEL2_HEADING_RE.match(lines[idx])),
        len(lines),
    )
    return start_idx, end_idx


def check_section12_conclusions(report_text: str) -> list:
    lines = report_text.splitlines()
    loc = find_level2_section(lines, SECTION12_HEADING_RE)
    if loc is None:
        return ["missing section heading `## 12 结论、证据与缺点`"]

    start_idx, end_idx = loc
    block = lines[start_idx + 1 : end_idx]

    conclusion_lines: list[tuple[str, str]] = []
    for line in block:
        match = CONCLUSION_BULLET_RE.match(line)
        if not match:
            continue
        conclusion_id = match.group(1).strip()
        conclusion_text = match.group(2).strip()
        conclusion_lines.append((conclusion_id, conclusion_text))

    if len(conclusion_lines) < 3:
        return [f"section 12 must include at least 3 conclusions (A/B/C). Found: {len(conclusion_lines)}"]

    issues: list[str] = []
    for conclusion_id, conclusion_text in conclusion_lines:
        if not conclusion_text:
            issues.append(f"section 12 conclusion {conclusion_id} is blank")
            continue
        if conclusion_text == "本文不涉及":
            issues.append(f"section 12 conclusion {conclusion_id} must not be `本文不涉及`")
        # Require evidence footnotes in section-12 numbering scheme.
        if not FOOTNOTE_REF_CH12_RE.search(conclusion_text):
            issues.append(f"section 12 conclusion {conclusion_id} missing evidence footnote like [^12-1]")

    return issues


def check_llm_reflection_section(report_text: str, summary_mode: str) -> list:
    if summary_mode != "精读":
        return []

    lines = report_text.splitlines()
    loc = find_level2_section(lines, LLM_REFLECTION_HEADING_RE)
    if loc is None:
        return ["missing section heading `## 14 复盘评分与发表定位`"]

    start_idx, end_idx = loc
    block = lines[start_idx + 1 : end_idx]

    found_scores: dict[str, str] = {}
    for line in block:
        match = SCORE_BULLET_RE.match(line)
        if not match:
            continue
        label = match.group(1).strip()
        content = match.group(2).strip()
        found_scores[label] = content

    required = ["创新性", "叙事性", "复现性"]
    missing = [item for item in required if item not in found_scores]
    if missing:
        return [f"section 14 missing score lines: {', '.join(missing)}"]

    issues: list[str] = []
    for label in required:
        content = found_scores.get(label, "").strip()
        if not content:
            issues.append(f"section 14 {label} is blank")
            continue
        if content == "本文不涉及":
            issues.append(f"section 14 {label} must not be `本文不涉及`")

        content_no_notes = FOOTNOTE_REF_RE.sub("", content)
        score_match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:/10)?\s*", content_no_notes)
        if not score_match:
            issues.append(f"section 14 {label} must start with a numeric score (0-10)")
            continue
        try:
            score_val = float(score_match.group(1))
        except Exception:
            score_val = None
        if score_val is None or score_val < 0 or score_val > 10:
            issues.append(f"section 14 {label} score must be within 0-10")

        # Require narrative beyond just the score.
        narrative = content_no_notes[score_match.end() :].strip()
        narrative_clean = re.sub(r"\d+(?:\.\d+)?(?:\s*/\s*10)?", "", narrative)
        narrative_clean = re.sub(r"[\s\W_]+", "", narrative_clean, flags=re.UNICODE)
        if len(narrative_clean) < 10:
            issues.append(f"section 14 {label} must include a short narrative explanation beyond the score")

        if not FOOTNOTE_REF_CH14_RE.search(content):
            issues.append(f"section 14 {label} missing evidence footnote like [^14-1]")

    # Venue positioning & publishability reasoning.
    published_venue_line = next((ln for ln in block if PUBLISHED_VENUE_BULLET_RE.match(ln)), None)
    is_preprint = False
    if published_venue_line is None:
        issues.append("section 14 missing `- 论文实际发表：...`")
    else:
        match = PUBLISHED_VENUE_BULLET_RE.match(published_venue_line)
        if not match:
            issues.append("section 14 published-venue line has unexpected format")
        else:
            venue_content = match.group(1).strip()
            if not venue_content:
                issues.append("section 14 published-venue line is blank")
            if venue_content == "本文不涉及":
                issues.append("section 14 published-venue line must not be `本文不涉及`")
            venue_content_no_notes = FOOTNOTE_REF_RE.sub("", venue_content).strip()
            venue_content_norm = venue_content_no_notes.lower()
            if any(marker in venue_content_no_notes or marker in venue_content_norm for marker in PREPRINT_MARKERS):
                is_preprint = True
            if not FOOTNOTE_REF_CH14_RE.search(published_venue_line):
                issues.append("section 14 published-venue line missing evidence footnote like [^14-1]")

    venue_tier_line = next((ln for ln in block if VENUE_TIER_BULLET_RE.match(ln)), None)
    if venue_tier_line is None:
        if not is_preprint:
            issues.append("section 14 missing `- 发表...档位判断：...`")
    else:
        match = VENUE_TIER_BULLET_RE.match(venue_tier_line)
        if not match:
            issues.append("section 14 venue tier line has unexpected format")
        else:
            tier_content = match.group(1).strip()
            tier_content_no_notes = FOOTNOTE_REF_RE.sub("", tier_content).strip()
            tier_content_norm = tier_content_no_notes.lower()

            # If preprint, venue-tier evaluation is optional: allow blank/omitted.
            if is_preprint and (not tier_content_no_notes or tier_content_no_notes == "本文不涉及" or any(m in tier_content_norm for m in PREPRINT_MARKERS)):
                pass
            else:
                if not tier_content_no_notes:
                    issues.append("section 14 venue tier line is blank")
                if tier_content_no_notes == "本文不涉及":
                    issues.append("section 14 venue tier line must not be `本文不涉及`")
                if not any(token in tier_content_no_notes for token in ("顶级", "中等", "一般")):
                    issues.append("section 14 venue tier line must state one of: 顶级 / 中等 / 一般")
                if not FOOTNOTE_REF_CH14_RE.search(venue_tier_line):
                    issues.append("section 14 venue tier line missing evidence footnote like [^14-1]")

    venue_fit_line = next((ln for ln in block if VENUE_FIT_BULLET_RE.match(ln)), None)
    if venue_fit_line is None:
        if not is_preprint:
            issues.append("section 14 missing `- 为什么能发表在该...：...`")
    else:
        match = VENUE_FIT_BULLET_RE.match(venue_fit_line)
        if not match:
            issues.append("section 14 venue-fit line has unexpected format")
        else:
            fit_content = match.group(1).strip()
            fit_content_no_notes = FOOTNOTE_REF_RE.sub("", fit_content).strip()
            fit_content_norm = fit_content_no_notes.lower()

            # If preprint, venue-fit explanation is optional: allow blank/omitted.
            if is_preprint and (not fit_content_no_notes or fit_content_no_notes == "本文不涉及" or any(m in fit_content_norm for m in PREPRINT_MARKERS)):
                pass
            else:
                if not fit_content_no_notes:
                    issues.append("section 14 venue-fit line is blank")
                if fit_content_no_notes == "本文不涉及":
                    issues.append("section 14 venue-fit line must not be `本文不涉及`")
                if not FOOTNOTE_REF_CH14_RE.search(venue_fit_line):
                    issues.append("section 14 venue-fit line missing evidence footnote like [^14-1]")

    # Publishability reasoning: prefer single `- 可发表性推演：...` and allow nested bullets; fallback to legacy per-tier lines.
    publishability_idx = next((idx for idx, ln in enumerate(block) if PUBLISHABILITY_BULLET_RE.match(ln)), None)

    def _indent(line: str) -> int:
        expanded = line.expandtabs(4)
        return len(expanded) - len(expanded.lstrip(" "))

    if publishability_idx is not None:
        base_line = block[publishability_idx]
        match = PUBLISHABILITY_BULLET_RE.match(base_line)
        base_indent = _indent(base_line)
        parts: list[str] = []
        if match:
            first = match.group(1).strip()
            if first:
                parts.append(first)

        for ln in block[publishability_idx + 1 :]:
            if not ln.strip():
                continue
            if re.match(r"^\s*-\s+", ln) and _indent(ln) <= base_indent:
                break
            parts.append(ln.strip())

        content_blob = " ".join(parts).strip()
        if not content_blob:
            issues.append("section 14 publishability block is blank (fill `- 可发表性推演：...`)")
        elif content_blob == "本文不涉及":
            issues.append("section 14 publishability block must not be `本文不涉及`")
        else:
            if not FOOTNOTE_REF_CH14_RE.search(content_blob):
                issues.append("section 14 publishability block missing evidence footnote like [^14-1]")
            content_no_notes = FOOTNOTE_REF_RE.sub("", content_blob)
            missing_tiers = [tier for tier in ("顶级", "中等", "一般") if tier not in content_no_notes]
            if missing_tiers:
                issues.append("section 14 publishability block must cover tiers: 顶级 / 中等 / 一般")

            narrative_clean = re.sub(r"顶级|中等|一般", "", content_no_notes)
            narrative_clean = re.sub(r"[\s\W_]+", "", narrative_clean, flags=re.UNICODE)
            if len(narrative_clean) < 20:
                issues.append("section 14 publishability block must include brief reasoning, not just tier labels")
    else:
        pub_tiers_found: set[str] = set()
        for ln in block:
            match = PUB_TIER_BULLET_RE.match(ln)
            if not match:
                continue
            tier = match.group(1).strip()
            content = match.group(2).strip()
            pub_tiers_found.add(tier)
            if not content:
                issues.append(f"section 14 publishability line ({tier}) is blank")
            if content == "本文不涉及":
                issues.append(f"section 14 publishability line ({tier}) must not be `本文不涉及`")
            if not FOOTNOTE_REF_CH14_RE.search(ln):
                issues.append(f"section 14 publishability line ({tier}) missing evidence footnote like [^14-1]")

        if not pub_tiers_found:
            issues.append("section 14 missing publishability reasoning (add `- 可发表性推演：...`)")
        else:
            for tier in ("顶级", "中等", "一般"):
                if tier not in pub_tiers_found:
                    issues.append(f"section 14 missing publishability line for tier: {tier}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check if summary report is still template-like.")
    parser.add_argument("--artifact-dir", required=True, help="Paper artifact directory.")
    parser.add_argument(
        "--min-chars",
        type=int,
        default=0,
        help="Minimum characters. Use 0 to auto-select by summary_mode (精读=1800, 略读=600).",
    )
    parser.add_argument(
        "--max-blank-fields",
        type=int,
        default=12,
        help="Fail when blank field bullets exceed this threshold.",
    )
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).expanduser().resolve()
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise SystemExit(f"[ERROR] artifact_dir not found: {artifact_dir}")

    metadata = load_metadata(artifact_dir)
    summary_path = load_summary_path(metadata, artifact_dir)
    if not summary_path.exists():
        raise SystemExit(f"[ERROR] summary report not found: {summary_path}")

    text = summary_path.read_text(encoding="utf-8")
    issues = []
    summary_mode = normalize_summary_mode(str(metadata.get("summary_mode", "精读")))
    template_path, expected_headings = load_template_headings(summary_mode)
    actual_headings = extract_level2_headings(text)
    min_chars = args.min_chars if args.min_chars > 0 else (600 if summary_mode == "略读" else 1800)

    for token in PLACEHOLDER_TOKENS:
        if token in text:
            issues.append(f"contains placeholder token: {token}")

    for phrase in DISALLOWED_PHRASES:
        if phrase in text:
            issues.append(f"contains disallowed phrase: {phrase}")

    for tag in LEGACY_JUDGMENT_TAGS:
        if tag in text:
            issues.append(f"contains legacy judgment label: {tag}")

    if OTHER_NOT_INVOLVED_RE.search(text):
        issues.append("contains meaningless '其它:本文不涉及'; omit the `其它：` line when unused")

    blank_fields = sum(
        1
        for ln in text.splitlines()
        if BLANK_FIELD_RE.match(ln) or BLANK_NUMBERED_FIELD_RE.match(ln) or BLANK_CLAIM_RE.match(ln)
    )
    if blank_fields > args.max_blank_fields:
        issues.append(f"too many blank fields: {blank_fields} > {args.max_blank_fields}")

    if len(text.strip()) < min_chars:
        issues.append(f"too short: {len(text.strip())} < min_chars({min_chars})")

    issues.extend(check_section_heading_integrity(text, expected_headings))
    issues.extend(check_footnote_section_placement(text))
    issues.extend(check_figure_section_format(text))
    issues.extend(check_footnote_integrity(text))
    issues.extend(check_markdown_media_syntax(text))
    issues.extend(check_missing_wording(text))
    issues.extend(check_section12_conclusions(text))
    issues.extend(check_llm_reflection_section(text, summary_mode))
    footnote_refs = extract_footnote_refs(text)
    footnote_defs = set(parse_footnote_blocks(text).keys())

    print(f"summary_file={summary_path}")
    print(f"summary_mode={summary_mode}")
    print(f"heading_template={template_path}")
    print(f"section_headings={len(actual_headings)}")
    print(f"min_chars={min_chars}")
    print(f"chars={len(text.strip())}")
    print(f"blank_fields={blank_fields}")
    print(f"footnote_refs={len(footnote_refs)}")
    print(f"footnote_defs={len(footnote_defs)}")
    if issues:
        print("[FAIL] report still looks like template:")
        for issue in issues:
            print(f"- {issue}")
        return 2

    print("[OK] report looks finalized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
