#!/usr/bin/env python3
"""
Extract paper artifacts from a PDF for downstream paper-reading workflows.

Outputs include:
- full text by page
- URL candidates and categorized resource links
- figure/table caption candidates
- code-like signal lines
- data-availability snippets
- optional table extraction (pdfplumber)
- optional image extraction (pymupdf)
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from pypdf import PdfReader

try:
    import pdfplumber  # type: ignore
except ImportError:
    pdfplumber = None

try:
    import fitz  # type: ignore
except ImportError:
    fitz = None


URL_RE = re.compile(r"https?://[^\s<>\]})\"']+")
FIGURE_CAPTION_RE = re.compile(
    r"^\s*(?:FIGURE\s*[A-Za-z0-9]+\s+.+|(?:Figure|Fig\.|FIG\.)\s*[A-Za-z0-9]+(\s*\||\s*[:.])\s+.+)"
)
CAPTION_KEY_RE = re.compile(r"^\s*(Figure|FIGURE|Fig\.|FIG\.)\s*([A-Za-z0-9]+)")
TABLE_CAPTION_KEY_RE = re.compile(r"^\s*(Table|TABLE|Tab\.|TAB\.)\s*([A-Za-z0-9]+)")
TABLE_CAPTION_RE = re.compile(
    r"^\s*(?:TABLE\s*[A-Za-z0-9]+\s+.+|(?:Table|Tab\.|TAB\.)\s*[A-Za-z0-9]+(\s*\||\s*[:.])\s+.+)"
)
CITATION_STEM_RE = re.compile(r"^[^-]{1,80}\s-\s\d{4}\s-\s[^-]{1,120}\s-\s(.+)$")
CODE_SIGNAL_RE = re.compile(
    r"(Algorithm\s*\d+|pseudocode|code availability|source code|GitHub|gitlab|docker|conda|pip install|python\s+)",
    re.IGNORECASE,
)
AVAILABILITY_SIGNAL_RE = re.compile(
    r"(data availability|code availability|availability statement|source code|repository|zenodo|bioproject|sra)",
    re.IGNORECASE,
)


def normalize_name(raw: str) -> str:
    base = raw.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-{2,}", "-", base).strip("-")
    return base or "paper"


def safe_paper_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    name = name.rstrip(".")
    return name or "paper"


def extract_paper_title(pdf_path: Path, reader: PdfReader) -> str:
    metadata = reader.metadata or {}
    raw_title = str(metadata.get("/Title") or metadata.get("Title") or "").strip()
    raw_title = re.sub(r"\s+", " ", raw_title).strip()

    if raw_title:
        m = CITATION_STEM_RE.match(raw_title)
        if m:
            raw_title = m.group(1).strip()
        if len(raw_title) >= 10:
            return raw_title

    stem = pdf_path.stem.strip()
    m = CITATION_STEM_RE.match(stem)
    if m:
        stem = m.group(1).strip()
    return stem or "paper"


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary_template(paper_name: str, template_path: Path) -> str:
    output_lines: List[str] = [f"# {paper_name}阅读总结", ""]
    if not template_path.exists():
        output_lines.extend(
            [
                "# 0) 论文信息",
                "- 标题：",
                "",
                "# 1) 阅读总结",
                "- 核心贡献：",
            ]
        )
        return "\n".join(output_lines).rstrip() + "\n"

    lines = template_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith("# "):
            continue
        output_lines.append(line)

    content = "\n".join(output_lines)
    content = content.replace(
        "`![图说明](/absolute/path/to/image.png)`",
        "`![图说明](images/your-figure.png)`",
    )
    return content.rstrip() + "\n"


def normalize_summary_mode(raw: str) -> str:
    mode = str(raw).strip().lower()
    if mode in {"short", "略读", "lue-du", "skim"}:
        return "略读"
    if mode in {"long", "精读", "jingdu"}:
        return "精读"
    raise ValueError(f"unsupported summary mode: {raw}")


def write_image_gallery(path: Path, manifest: List[Dict[str, object]]) -> None:
    lines: List[str] = ["# Image Gallery", ""]
    if not manifest:
        lines.append("未提取到图片。")
        write_text(path, "\n".join(lines) + "\n")
        return

    for item in manifest:
        page = item.get("page", "?")
        source = str(item.get("source", "embedded"))
        image_index = item.get("image_index", item.get("render_index", "?"))
        crop_note = ""
        if source == "page_render":
            crop_mode = str(item.get("crop_mode", "none"))
            crop_applied = bool(item.get("crop_applied", False))
            crop_note = f" / crop={crop_mode}"
            if crop_applied:
                crop_note += "(applied)"
        abs_img_path = Path(str(item.get("path", "")))
        rel_img_path = abs_img_path
        try:
            rel_img_path = abs_img_path.relative_to(path.parent)
        except Exception:
            try:
                rel_img_path = Path(
                    str(abs_img_path).replace(str(path.parent) + "/", "", 1)
                )
            except Exception:
                rel_img_path = abs_img_path
        rel_str = str(rel_img_path)
        lines.append(f"## Page {page} / {source} / Image {image_index}{crop_note}")
        lines.append(f"`{rel_str}`")
        lines.append(f"![page-{page}-image-{image_index}]({rel_str})")
        lines.append("")
    write_text(path, "\n".join(lines).rstrip() + "\n")


def extract_annotation_urls(page) -> List[str]:
    urls: List[str] = []
    annots = page.get("/Annots")
    if not annots:
        return urls

    for annot_ref in annots:
        try:
            annot = annot_ref.get_object()
            action = annot.get("/A")
            if action and action.get("/URI"):
                uri = str(action.get("/URI")).strip()
                if uri.startswith("http://") or uri.startswith("https://"):
                    urls.append(uri)
        except Exception:
            continue
    return urls


def clean_url(url: str) -> str:
    return url.rstrip(".,;:)")


def is_usable_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or ""
    if parsed.scheme not in {"http", "https"}:
        return False
    if "." not in host:
        return False
    if url in {"https://doi", "https://doi.org/", "https://doi.org/10"}:
        return False
    if host == "doi.org":
        if not re.match(r"^/10\.\S+", path):
            return False
        if path.endswith("-") or path.endswith("/"):
            return False
    return True


def categorize_url(url: str, context: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    full = f"{host} {url.lower()} {context.lower()}"

    if any(token in full for token in ["github.com", "gitlab.com", "bitbucket.org", "source code", "docker"]):
        return "code"
    if any(token in full for token in ["ncbi.nlm.nih.gov", "bioproject", "sra", "zenodo", "figshare", "dryad", "kaggle"]):
        return "data"
    if any(token in full for token in ["supplement", "video", "slides", "imeta.science", "update materials"]):
        return "supplementary"
    if "doi.org" in host:
        return "doi"
    return "other"


def collect_section_snippets(page_lines: List[Tuple[int, List[str]]], window: int = 3) -> List[Dict[str, object]]:
    snippets: List[Dict[str, object]] = []
    for page_no, lines in page_lines:
        for idx, line in enumerate(lines):
            if AVAILABILITY_SIGNAL_RE.search(line):
                start = max(0, idx - window)
                end = min(len(lines), idx + window + 1)
                snippets.append(
                    {
                        "page": page_no,
                        "trigger_line": line.strip(),
                        "snippet": " ".join(l.strip() for l in lines[start:end] if l.strip()),
                    }
                )
    return snippets


def collapse_parent_urls(urls: Set[str]) -> List[str]:
    reduced = set(urls)
    for url in list(reduced):
        if url.endswith("/") and any(other != url and other.startswith(url) for other in reduced):
            reduced.discard(url)
    return sorted(reduced)


def extract_tables(pdf_path: Path) -> List[Dict[str, object]]:
    if pdfplumber is None:
        return []

    table_results: List[Dict[str, object]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table_idx, table in enumerate(tables, start=1):
                cleaned_rows = []
                for row in table:
                    if row is None:
                        continue
                    cleaned_rows.append([cell.strip() if isinstance(cell, str) else cell for cell in row])
                table_results.append(
                    {
                        "page": page_idx,
                        "table_index": table_idx,
                        "rows": cleaned_rows,
                        "n_rows": len(cleaned_rows),
                        "n_cols": max((len(r) for r in cleaned_rows), default=0),
                    }
                )
    return table_results


def extract_embedded_images(
    pdf_path: Path,
    image_dir: Path,
    prefix: str,
    min_width: int,
    min_height: int,
    min_area: int,
    skip_pages: Optional[Set[int]] = None,
) -> List[Dict[str, object]]:
    if fitz is None:
        return []

    image_dir.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, object]] = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_idx in range(len(doc)):
            if skip_pages and (page_idx + 1) in skip_pages:
                continue
            page = doc[page_idx]
            images = page.get_images(full=True)
            for img_idx, img in enumerate(images, start=1):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception:
                    continue

                width = int(getattr(pix, "width", 0) or 0)
                height = int(getattr(pix, "height", 0) or 0)
                if width < min_width or height < min_height or (width * height) < min_area:
                    pix = None
                    continue

                color_channels = int(getattr(pix, "n", 0) or 0) - int(bool(getattr(pix, "alpha", False)))
                if color_channels > 3:
                    try:
                        pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                    except Exception:
                        pix = None
                        continue
                    pix = pix_rgb
                    width = int(getattr(pix, "width", 0) or width)
                    height = int(getattr(pix, "height", 0) or height)

                filename = f"{prefix}_p{page_idx + 1:03d}_img{img_idx:03d}_xref{xref}.png"
                out_path = image_dir / filename
                try:
                    pix.save(str(out_path))
                except Exception:
                    pix = None
                    continue
                manifest.append(
                    {
                        "source": "embedded",
                        "page": page_idx + 1,
                        "image_index": img_idx,
                        "xref": xref,
                        "ext": "png",
                        "width": width,
                        "height": height,
                        "alpha": bool(getattr(pix, "alpha", False)),
                        "colorspace": str(getattr(getattr(pix, "colorspace", None), "name", "") or ""),
                        "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
                        "path": str(out_path),
                    }
                )
                pix = None
    finally:
        doc.close()
    return manifest


def select_render_pages(
    num_pages: int,
    captions: List[Dict[str, object]],
    mode: str,
    max_captions_per_page: int,
) -> List[int]:
    if mode == "all":
        return list(range(1, num_pages + 1))

    caption_counts: Dict[int, int] = {}
    for item in captions:
        page = int(item.get("page", 0))
        if page > 0:
            caption_counts[page] = caption_counts.get(page, 0) + 1

    pages = sorted(caption_counts.keys())
    filtered_pages = [page for page in pages if caption_counts.get(page, 0) <= max_captions_per_page]
    if filtered_pages:
        return filtered_pages
    if pages:
        return pages
    return list(range(1, num_pages + 1))


def find_caption_line_rects(page) -> List["fitz.Rect"]:
    if fitz is None:
        return []

    rects: List["fitz.Rect"] = []
    try:
        text_dict = page.get_text("dict")
    except Exception:
        return rects

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not text:
                continue
            if FIGURE_CAPTION_RE.match(text) or TABLE_CAPTION_RE.match(text):
                bbox = line.get("bbox")
                if bbox and len(bbox) == 4:
                    rects.append(fitz.Rect(*bbox))
    return rects


def caption_query_from_line(line: str) -> Optional[str]:
    stripped = line.strip()
    for pattern in (CAPTION_KEY_RE, TABLE_CAPTION_KEY_RE):
        m = pattern.match(stripped)
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return None


def rect_area(rect) -> float:
    return float(rect.width) * float(rect.height)


def horizontal_overlap_ratio(a, b) -> float:
    inter = max(0.0, min(float(a.x1), float(b.x1)) - max(float(a.x0), float(b.x0)))
    denom = max(1.0, min(float(a.width), float(b.width)))
    return inter / denom


def collect_visual_rects(
    page,
    min_image_area_ratio: float,
    min_drawing_area_ratio: float,
) -> List["fitz.Rect"]:
    if fitz is None:
        return []

    page_rect = page.rect
    page_area = max(1.0, float(page_rect.width) * float(page_rect.height))
    rects: List["fitz.Rect"] = []
    seen: Set[Tuple[float, float, float, float]] = set()

    try:
        page_images = page.get_images(full=True) or []
    except Exception:
        page_images = []
    for img in page_images:
        xref = img[0]
        try:
            hits = page.get_image_rects(xref) or []
        except Exception:
            hits = []
        for rect in hits:
            try:
                if (rect_area(rect) / page_area) < float(min_image_area_ratio):
                    continue
            except Exception:
                continue
            key = (round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1))
            if key in seen:
                continue
            seen.add(key)
            rects.append(rect)

    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if not rect:
            continue
        try:
            if (rect_area(rect) / page_area) < float(min_drawing_area_ratio):
                continue
        except Exception:
            continue
        key = (round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1))
        if key in seen:
            continue
        seen.add(key)
        rects.append(rect)

    return rects


def has_visual_signal(
    page,
    min_image_area_ratio: float,
    min_drawing_area_ratio: float,
    min_drawings_count: int,
) -> bool:
    if fitz is None:
        return False

    if collect_visual_rects(
        page=page,
        min_image_area_ratio=min_image_area_ratio,
        min_drawing_area_ratio=min_drawing_area_ratio,
    ):
        return True

    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    return len(drawings) >= int(min_drawings_count)


def build_caption_aware_clip(
    page,
    caption_top_margin_pt: float,
    crop_bottom_margin_pt: float,
    min_crop_height_ratio: float,
    caption_queries: List[str],
) -> Tuple[Optional["fitz.Rect"], int]:
    if fitz is None:
        return None, 0

    caption_rects = find_caption_line_rects(page)
    if not caption_rects and caption_queries:
        for query in caption_queries:
            try:
                hits = page.search_for(query)
            except Exception:
                hits = []
            caption_rects.extend(hits)
    caption_count = len(caption_rects)
    page_rect = page.rect

    # Visual candidates include embedded images (common for photos) and vector drawings
    # (common for plots/diagrams in scientific PDFs).
    visual_rects = collect_visual_rects(
        page=page,
        min_image_area_ratio=0.002,
        min_drawing_area_ratio=0.01,
    )
    if not visual_rects:
        return None, caption_count

    if caption_rects:
        max_gap = float(page_rect.height) * 0.25
        filtered_caps: List["fitz.Rect"] = []
        for cap in caption_rects:
            best_gap: Optional[float] = None
            for vr in visual_rects:
                gap = 0.0
                if float(vr.y1) <= float(cap.y0):
                    gap = float(cap.y0) - float(vr.y1)
                elif float(vr.y0) >= float(cap.y1):
                    gap = float(vr.y0) - float(cap.y1)
                if best_gap is None or gap < best_gap:
                    best_gap = gap
            if best_gap is not None and best_gap <= max_gap:
                filtered_caps.append(cap)
        caption_rects = filtered_caps

    rects_to_union: List["fitz.Rect"] = []
    if caption_rects:
        tol = max(6.0, float(page_rect.height) * 0.01)
        for cap in caption_rects:
            above = [vr for vr in visual_rects if float(vr.y1) <= float(cap.y0) + tol]
            below = [vr for vr in visual_rects if float(vr.y0) >= float(cap.y1) - tol]
            above_area = sum(rect_area(vr) for vr in above)
            below_area = sum(rect_area(vr) for vr in below)
            if above_area <= 0 and below_area <= 0:
                continue
            candidates = above if above_area >= below_area else below
            if not candidates:
                continue
            rects_to_union.extend(candidates)
            rects_to_union.append(cap)

    if not rects_to_union:
        rects_to_union.extend(visual_rects)

    x0 = min(float(r.x0) for r in rects_to_union)
    y0 = min(float(r.y0) for r in rects_to_union)
    x1 = max(float(r.x1) for r in rects_to_union)
    y1 = max(float(r.y1) for r in rects_to_union)

    pad = float(caption_top_margin_pt)
    left = max(float(page_rect.x0), x0 - pad)
    top = max(float(page_rect.y0), y0 - pad)
    right = min(float(page_rect.x1), x1 + pad)
    bottom_limit = float(page_rect.y1) - float(crop_bottom_margin_pt)
    bottom = min(bottom_limit, y1 + pad)

    right = max(left + 1.0, right)
    bottom = max(top + 1.0, bottom)

    clip = fitz.Rect(left, top, right, bottom)
    if float(clip.height) < (float(page_rect.height) * float(min_crop_height_ratio)):
        return None, caption_count
    return clip, caption_count


def render_figure_pages(
    pdf_path: Path,
    image_dir: Path,
    prefix: str,
    pages_to_render: List[int],
    dpi: int,
    crop_mode: str,
    caption_top_margin_pt: float,
    crop_bottom_margin_pt: float,
    min_crop_height_ratio: float,
    caption_queries_by_page: Dict[int, List[str]],
) -> List[Dict[str, object]]:
    if fitz is None:
        return []

    image_dir.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, object]] = []
    doc = fitz.open(str(pdf_path))
    scale = max(1.0, float(dpi) / 72.0)
    matrix = fitz.Matrix(scale, scale)
    try:
        for idx, page_no in enumerate(pages_to_render, start=1):
            if page_no < 1 or page_no > len(doc):
                continue
            page = doc[page_no - 1]
            clip_rect = None
            caption_rect_count = 0
            if crop_mode == "caption-aware":
                caption_queries = caption_queries_by_page.get(page_no, [])
                clip_rect, caption_rect_count = build_caption_aware_clip(
                    page=page,
                    caption_top_margin_pt=caption_top_margin_pt,
                    crop_bottom_margin_pt=crop_bottom_margin_pt,
                    min_crop_height_ratio=min_crop_height_ratio,
                    caption_queries=caption_queries,
                )

            pix = page.get_pixmap(matrix=matrix, alpha=False, clip=clip_rect)
            filename = f"{prefix}_p{page_no:03d}_render_{dpi}dpi"
            if clip_rect is not None:
                filename += "_capcrop"
            filename += ".png"
            out_path = image_dir / filename
            pix.save(str(out_path))
            manifest.append(
                {
                    "source": "page_render",
                    "page": page_no,
                    "render_index": idx,
                    "dpi": dpi,
                    "width": pix.width,
                    "height": pix.height,
                    "size_bytes": out_path.stat().st_size,
                    "crop_mode": crop_mode,
                    "crop_applied": clip_rect is not None,
                    "caption_rect_count": caption_rect_count,
                    "clip_rect": [clip_rect.x0, clip_rect.y0, clip_rect.x1, clip_rect.y1] if clip_rect is not None else None,
                    "path": str(out_path),
                }
            )
    finally:
        doc.close()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PDF artifacts for paper-reading skill.")
    parser.add_argument("pdf", help="Absolute path to the target PDF.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Root directory for outputs (default: current directory). In bundle layout, artifacts go to <output-dir>/<bundle-name>/.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Legacy artifact prefix for file naming; bundle directory name comes from extracted title or --bundle-name.",
    )
    parser.add_argument(
        "--bundle-name",
        default=None,
        help="Override bundle directory name (layout=bundle). Useful for short aliases like HELIX_NatComputSci.",
    )
    parser.add_argument(
        "--layout",
        choices=["bundle", "flat"],
        default="bundle",
        help="Output layout. 'bundle' writes to <output-dir>/<bundle-name>/ and keeps files grouped. 'flat' keeps legacy prefix_file layout.",
    )
    parser.add_argument(
        "--summary-mode",
        default="精读",
        help="Summary template mode. Use 略读 or 精读 (short/long kept for compatibility).",
    )
    parser.add_argument(
        "--summary-init",
        choices=["none", "template"],
        default="none",
        help="Initialize summary file with template or not. Default 'none' avoids leaving template-only reports.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean existing artifacts for the same prefix before writing new outputs.",
    )
    parser.add_argument(
        "--image-mode",
        choices=["embedded", "render", "hybrid"],
        default="hybrid",
        help="Image extraction strategy. 'hybrid' combines filtered embedded images and rendered figure pages.",
    )
    parser.add_argument(
        "--figure-pages",
        choices=["caption", "all"],
        default="caption",
        help="Pages to render in render/hybrid image modes.",
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=220,
        help="DPI for page rendering in render/hybrid image modes.",
    )
    parser.add_argument(
        "--render-crop-mode",
        choices=["none", "caption-aware"],
        default="caption-aware",
        help="Crop strategy for render/hybrid mode. caption-aware crops to visual regions near detected captions (fallbacks to visual bounding boxes).",
    )
    parser.add_argument(
        "--caption-top-margin-pt",
        type=float,
        default=10.0,
        help="Top margin (pt) added above detected figure caption in caption-aware crop mode.",
    )
    parser.add_argument(
        "--crop-bottom-margin-pt",
        type=float,
        default=8.0,
        help="Bottom margin (pt) removed from page bottom in caption-aware crop mode.",
    )
    parser.add_argument(
        "--min-crop-height-ratio",
        type=float,
        default=0.15,
        help="Fallback to full-page render when computed crop height is smaller than this fraction of page height.",
    )
    parser.add_argument(
        "--max-captions-per-render-page",
        type=int,
        default=6,
        help="When --figure-pages=caption, skip pages with too many caption hits (often supplementary lists).",
    )
    parser.add_argument("--embedded-min-width", type=int, default=400, help="Min width for embedded images.")
    parser.add_argument("--embedded-min-height", type=int, default=300, help="Min height for embedded images.")
    parser.add_argument("--embedded-min-area", type=int, default=120000, help="Min area (w*h) for embedded images.")
    parser.add_argument(
        "--keep-embedded-on-rendered-pages",
        action="store_true",
        help="In hybrid mode, keep embedded images even when the same page is rendered.",
    )
    args = parser.parse_args()
    try:
        summary_mode = normalize_summary_mode(args.summary_mode)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    pdf_path = Path(args.pdf).expanduser().resolve()
    base_out_dir = Path(args.output_dir).expanduser().resolve()
    base_out_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    reader = PdfReader(str(pdf_path))
    paper_title = extract_paper_title(pdf_path=pdf_path, reader=reader)
    extracted_name = safe_paper_name(paper_title)
    bundle_name = safe_paper_name(str(args.bundle_name)) if args.bundle_name else extracted_name
    prefix = normalize_name(args.prefix if args.prefix else bundle_name)
    summary_filename = f"{extracted_name}阅读总结.md"

    if args.layout == "bundle":
        run_out_dir = base_out_dir / bundle_name
        if args.clean and run_out_dir.exists():
            shutil.rmtree(run_out_dir)
        run_out_dir.mkdir(parents=True, exist_ok=True)
        image_dir = run_out_dir / "images"
        summary_path = run_out_dir / summary_filename

        def path_for(name: str) -> Path:
            return run_out_dir / name

    else:
        run_out_dir = base_out_dir
        if args.clean:
            for old_file in base_out_dir.glob(f"{prefix}_*"):
                if old_file.is_dir():
                    shutil.rmtree(old_file, ignore_errors=True)
                else:
                    old_file.unlink(missing_ok=True)
        image_dir = base_out_dir / f"{prefix}_images"
        summary_path = base_out_dir / summary_filename

        def path_for(name: str) -> Path:
            return base_out_dir / f"{prefix}_{name}"

    page_text_parts: List[str] = []
    page_lines: List[Tuple[int, List[str]]] = []

    figure_captions: List[Dict[str, object]] = []
    table_captions: List[Dict[str, object]] = []
    code_signals: List[Dict[str, object]] = []

    all_urls: Set[str] = set()
    url_hits: List[Dict[str, object]] = []

    for page_idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = text.splitlines()
        page_lines.append((page_idx, lines))
        page_text_parts.append(f"\n\n===== Page {page_idx} =====\n{text}")

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if FIGURE_CAPTION_RE.match(line):
                figure_captions.append({"page": page_idx, "line": line})
            if TABLE_CAPTION_RE.match(line):
                table_captions.append({"page": page_idx, "line": line})
            if CODE_SIGNAL_RE.search(line):
                code_signals.append({"page": page_idx, "line": line})

            for match in URL_RE.findall(line):
                clean = clean_url(match)
                if clean and is_usable_url(clean):
                    all_urls.add(clean)
                    url_hits.append({"page": page_idx, "url": clean, "context": line})

        for uri in extract_annotation_urls(page):
            clean = clean_url(uri)
            if clean and is_usable_url(clean):
                all_urls.add(clean)
                url_hits.append({"page": page_idx, "url": clean, "context": "[annotation]"})

    metadata = {
        "pdf_path": str(pdf_path),
        "paper_title": paper_title,
        "paper_name": bundle_name,
        "paper_name_extracted": extracted_name,
        "bundle_name": bundle_name,
        "num_pages": len(reader.pages),
        "prefix": prefix,
        "layout": args.layout,
        "output_dir": str(run_out_dir),
        "summary_file": str(summary_path),
        "summary_mode": summary_mode,
        "summary_init": args.summary_init,
        "image_settings": {
            "image_mode": args.image_mode,
            "figure_pages": args.figure_pages,
            "render_dpi": args.render_dpi,
            "render_crop_mode": args.render_crop_mode,
            "caption_top_margin_pt": args.caption_top_margin_pt,
            "crop_bottom_margin_pt": args.crop_bottom_margin_pt,
            "min_crop_height_ratio": args.min_crop_height_ratio,
            "max_captions_per_render_page": args.max_captions_per_render_page,
            "embedded_min_width": args.embedded_min_width,
            "embedded_min_height": args.embedded_min_height,
            "embedded_min_area": args.embedded_min_area,
            "keep_embedded_on_rendered_pages": args.keep_embedded_on_rendered_pages,
        },
        "pdf_metadata": {k: str(v) for k, v in (reader.metadata or {}).items()},
        "optional_modules": {
            "pdfplumber": pdfplumber is not None,
            "pymupdf": fitz is not None,
        },
    }

    section_snippets = collect_section_snippets(page_lines)

    categorized: Dict[str, Set[str]] = {"code": set(), "data": set(), "supplementary": set(), "doi": set(), "other": set()}
    for hit in url_hits:
        url = str(hit["url"])
        context = str(hit["context"])
        category = categorize_url(url, context)
        categorized[category].add(url)

    resource_links = {key: collapse_parent_urls(value) for key, value in categorized.items()}

    availability_pages = {int(item["page"]) for item in section_snippets}
    priority_categorized: Dict[str, Set[str]] = {"code": set(), "data": set(), "supplementary": set(), "doi": set(), "other": set()}
    for hit in url_hits:
        page = int(hit["page"])
        context = str(hit["context"])
        if page not in availability_pages and not AVAILABILITY_SIGNAL_RE.search(context):
            continue
        url = str(hit["url"])
        category = categorize_url(url, context)
        priority_categorized[category].add(url)

    resource_links_priority = {key: collapse_parent_urls(value) for key, value in priority_categorized.items()}

    tables = extract_tables(pdf_path)
    caption_queries_by_page: Dict[int, List[str]] = {}
    for item in (figure_captions + table_captions):
        page = int(item.get("page", 0))
        line = str(item.get("line", ""))
        if page <= 0 or not line:
            continue
        query = caption_query_from_line(line)
        if not query:
            continue
        existing = caption_queries_by_page.setdefault(page, [])
        if query not in existing:
            existing.append(query)

    images_manifest: List[Dict[str, object]] = []
    pages_to_render: List[int] = []
    render_manifest: List[Dict[str, object]] = []
    if args.image_mode in {"render", "hybrid"}:
        pages_to_render = select_render_pages(
            num_pages=len(reader.pages),
            captions=(figure_captions + table_captions),
            mode=args.figure_pages,
            max_captions_per_page=args.max_captions_per_render_page,
        )
        render_manifest = render_figure_pages(
            pdf_path=pdf_path,
            image_dir=image_dir,
            prefix=prefix,
            pages_to_render=pages_to_render,
            dpi=args.render_dpi,
            crop_mode=args.render_crop_mode,
            caption_top_margin_pt=args.caption_top_margin_pt,
            crop_bottom_margin_pt=args.crop_bottom_margin_pt,
            min_crop_height_ratio=args.min_crop_height_ratio,
            caption_queries_by_page=caption_queries_by_page,
        )

    embedded_manifest: List[Dict[str, object]] = []
    if args.image_mode in {"embedded", "hybrid"}:
        embedded_skip_pages: Set[int] = set()
        if args.image_mode == "hybrid" and pages_to_render and not args.keep_embedded_on_rendered_pages:
            embedded_skip_pages = set(pages_to_render)
        embedded_manifest = extract_embedded_images(
            pdf_path=pdf_path,
            image_dir=image_dir,
            prefix=prefix,
            min_width=args.embedded_min_width,
            min_height=args.embedded_min_height,
            min_area=args.embedded_min_area,
            skip_pages=embedded_skip_pages,
        )

    images_manifest.extend(embedded_manifest)
    images_manifest.extend(render_manifest)

    metadata["image_settings"]["render_pages_selected"] = pages_to_render
    metadata["image_settings"]["caption_queries_by_page"] = caption_queries_by_page

    image_source_counts: Dict[str, int] = {}
    for item in images_manifest:
        src = str(item.get("source", "unknown"))
        image_source_counts[src] = image_source_counts.get(src, 0) + 1

    write_text(path_for("fulltext.txt"), "".join(page_text_parts))
    write_json(path_for("metadata.json"), metadata)
    write_text(path_for("urls_all.txt"), "\n".join(sorted(all_urls)))
    write_json(path_for("url_hits.json"), url_hits)
    write_json(path_for("resource_links.json"), resource_links)
    write_json(path_for("resource_links_priority.json"), resource_links_priority)
    write_json(path_for("figure_captions.json"), figure_captions)
    write_json(path_for("table_captions.json"), table_captions)
    write_json(path_for("code_signals.json"), code_signals)
    write_json(path_for("availability_snippets.json"), section_snippets)
    write_json(path_for("tables.json"), tables)
    write_json(path_for("images_manifest.json"), images_manifest)
    write_image_gallery(path_for("image_gallery.md"), images_manifest)
    if args.summary_init == "template":
        template_filename = "dna-deep-template.md" if summary_mode == "精读" else "dna-short-template.md"
        template_path = Path(__file__).resolve().parents[1] / "assets" / template_filename
        summary_md = build_summary_template(paper_name=paper_title, template_path=template_path)
        write_text(summary_path, summary_md)

    print(f"pdf={pdf_path}")
    print(f"layout={args.layout}")
    print(f"summary_mode={summary_mode}")
    print(f"summary_init={args.summary_init}")
    print(f"prefix={prefix}")
    print(f"image_mode={args.image_mode}")
    print(f"figure_pages={args.figure_pages}")
    print(f"render_dpi={args.render_dpi}")
    print(f"render_crop_mode={args.render_crop_mode}")
    print(f"max_captions_per_render_page={args.max_captions_per_render_page}")
    print(f"render_pages_selected={pages_to_render}")
    print(f"pages={len(reader.pages)}")
    print(f"urls={len(all_urls)}")
    print(f"figures={len(figure_captions)}")
    print(f"tables_captions={len(table_captions)}")
    print(f"code_signals={len(code_signals)}")
    print(f"availability_snippets={len(section_snippets)}")
    print(f"tables_extracted={len(tables)}")
    print(f"images_extracted={len(images_manifest)}")
    if image_source_counts:
        source_stats = ",".join(f"{k}:{v}" for k, v in sorted(image_source_counts.items()))
        print(f"images_by_source={source_stats}")
    print(f"output_dir={run_out_dir}")
    print(f"summary_file={summary_path}")
    print(f"summary_exists={summary_path.exists()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
