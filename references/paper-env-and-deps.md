# paper 环境与依赖配置

本技能的脚本默认在 conda 环境 `paper` 运行。

## 1) 依赖文件

- `scripts/requirements-paper.txt`
- `scripts/requirements-paper-optional.txt`

核心依赖（必须）：

- `pypdf`：基础文本与链接提取
- `PyYAML`：技能校验脚本依赖

可选依赖（增强）：

- `pdfplumber`：表格提取
- `PyMuPDF`：图片导出

## 2) 一键安装

在技能目录执行：

```bash
bash scripts/setup_paper_env.sh paper
```

如果你的环境名不是 `paper`，把参数改成目标环境名。

## 3) 手动安装（备选）

```bash
conda run -n paper python -m pip install -r scripts/requirements-paper.txt
```

安装可选增强依赖：

```bash
conda run -n paper python -m pip install -r scripts/requirements-paper-optional.txt
```

## 4) 环境验证

```bash
conda run -n paper python -c "import yaml,pypdf; print('core-deps-ok')"
```

可选依赖验证：

```bash
conda run -n paper python -c "import pdfplumber,fitz; print('optional-deps-ok')"
```

## 5) 提取脚本运行方式

```bash
conda run -n paper python scripts/extract_paper_artifacts.py \
  "/absolute/path/to/paper.pdf" \
  --bundle-name "<论文目录名或简称（可选）>" \
  --output-dir "/absolute/path/to/codex论文阅读" \
  --summary-mode 精读 \
  --summary-init none \
  --layout bundle \
  --clean
```

推荐把输出固定写到 `codex论文阅读` 工作区根目录，不要写到 `artifacts` 目录。
并在 `metadata.json` 中写出：`summary_file`（最终报告路径）。

如果你需要切换到其他目录，按下面方式指定输出根目录：

```bash
  --output-dir "/absolute/path/to/output_root"
```

此时输出会写到：

- `"/absolute/path/to/output_root/<论文名或--bundle-name>/"`

命名规则（bundle 布局）：

- 输出目录：`论文名`（或 `--bundle-name` 指定的简称，例如 `HELIX_NatComputSci`）
- 总结文件：`<论文题目>阅读总结.md`（从 PDF 元数据/文件名提取；与 `--bundle-name` 无关）
- 总结模式：`--summary-mode 精读`（默认）或 `--summary-mode 略读`
- 总结初始化：`--summary-init none`（默认，不生成模板文件，避免模板误交付）

## 5.2) 将 AI 最终报告写入 summary_file（必做）

方式 A：从现有 Markdown 文件写入

```bash
conda run -n paper python scripts/write_final_report.py \
  --artifact-dir "/absolute/path/to/<论文名或简称>" \
  --input-file "/tmp/final_report.md"
```

方式 B：从 stdin 写入

```bash
cat "/absolute/path/to/final_report.md" | \
conda run -n paper python scripts/write_final_report.py \
  --artifact-dir "/absolute/path/to/<论文名或简称>" \
  --from-stdin
```

注意：`conda run` 在部分环境下无法读取 stdin（`sys.stdin.read()` 为空）；更推荐方式 A（`--input-file`）。

写入后校验“不是模板”：

```bash
conda run -n paper python scripts/check_report_not_template.py \
  --artifact-dir "/absolute/path/to/<论文名或简称>"
```

`bundle` 布局能显著减少中间文件散落。

## 5.1) 图片提取推荐参数（解决“漏图/糊图/噪声图”）

默认建议：

```bash
conda run -n paper python scripts/extract_paper_artifacts.py \
  "/absolute/path/to/paper.pdf" \
  --bundle-name "<论文目录名或简称（可选）>" \
  --output-dir "/absolute/path/to/codex论文阅读" \
  --summary-mode 精读 \
  --summary-init none \
  --layout bundle \
  --clean \
  --image-mode hybrid \
  --figure-pages caption \
  --render-dpi 220 \
  --render-crop-mode caption-aware
```

参数含义：

- `--image-mode embedded`：只导出 PDF 内嵌位图，速度快但容易漏掉矢量图。
- `--image-mode render`：直接按页渲染图片，最稳健但文件更大。
- `--image-mode hybrid`：先导出内嵌图，再渲染图页；通常最适合论文阅读。
- `--figure-pages caption`：仅渲染检测到图标题的页面（默认）。
- `--figure-pages all`：渲染全部页面，适合图标题检测失败或版式复杂文档。
- `--render-dpi`：渲染分辨率，`220` 是质量与体积平衡点；看不清可升到 `260-300`。
- `--render-crop-mode caption-aware`：基于图注附近的视觉元素（位图/矢量）自动裁剪，通常可裁掉两栏正文；失败则回退为整页渲染，并会跳过“只有 Figure 引用但无图形内容”的页面。
- `--caption-top-margin-pt`：图注上方保留边距（默认 `10`）。
- `--crop-bottom-margin-pt`：页面底部裁掉边距（默认 `8`）。
- `--min-crop-height-ratio`：裁图过小则回退整页（默认 `0.15`）。
- `--embedded-min-width/height/area`：过滤小图标、logo 等噪声位图。
- `--max-captions-per-render-page`：`caption` 模式下，同页图标题命中数超过阈值则跳过该页渲染（默认 `6`，可过滤 Supplementary figure 列表页）。
- `--keep-embedded-on-rendered-pages`：`hybrid` 模式默认会丢弃已渲染页上的 embedded 图（常见残图）；加上此参数可保留。

常见问题与对策：

- 漏图（尤其矢量图）：
  - 先用 `--image-mode hybrid`；
  - 仍缺失时改 `--figure-pages all`。
- 图像发糊：
  - 提高 `--render-dpi` 到 `260` 或 `300`。
- 自动裁图裁得不理想：
  - 先保持 `--render-crop-mode caption-aware`；
  - 调整 `--caption-top-margin-pt`（更大保留更多图注上方内容）；
  - 调整 `--min-crop-height-ratio`（更大更容易回退整页）。
- 产物过多：
  - 提高 `--embedded-min-area`（如 `200000`），并保持 `--figure-pages caption`。
- 渲染出“图目录页/补充材料列表页”：
  - 保持 `--figure-pages caption`；
  - 确认 `--max-captions-per-render-page` 为 `6` 或更小。

## 6) 中间文件清理（可选）

清理旧版 flat 布局产物：

```bash
conda run -n paper python scripts/cleanup_artifacts.py \
  --target-dir "/absolute/path/to/output_dir" \
  --auto-delete-flat
```

## 7) 输出文件说明

- `fulltext.txt`：按页拼接文本
- `urls_all.txt`：提取到的全部 URL
- `resource_links.json`：按 code/data/supplementary/doi 分类后的链接
- `resource_links_priority.json`：优先链接（聚焦 Data/Code availability 邻域）
- `figure_captions.json`：图标题候选
- `table_captions.json`：表标题候选
- `code_signals.json`：代码/算法线索行
- `availability_snippets.json`：Data/Code availability 邻域片段
- `tables.json`：表格结构（需要 `pdfplumber`）
- `images_manifest.json` 与 `images/`：图像清单与导出的图片（需要 `PyMuPDF`）
- `image_gallery.md`：可直接粘贴到报告中的图片 Markdown 引用清单（相对路径）

## 8) 仅保留最终 md（清空中间文件，可选）

在单论文目录（bundle 目录）执行：

```bash
conda run -n paper python scripts/cleanup_artifacts.py \
  --target-dir "/absolute/path/to/<论文名或简称>" \
  --final-md-only \
  --report-name auto \
  --keep-file "image_gallery.md"
```

默认会保留：

- `<论文名或简称>阅读总结.md`
- `images/` 图片目录

如果你确实只要纯文本 md，可追加：

```bash
  --drop-images-dir \
  --strip-image-links
```
