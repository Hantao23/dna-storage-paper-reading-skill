---
name: paper-reading
description: 面向 DNA 存储领域实验型论文的结构化阅读技能。用于生成“略读”与“精读”两种报告，重点覆盖 DNA 信道设定、仿真实验与湿实验，并要求所有关键结论都附原文证据。
---

# 论文阅读（DNA 实验论文）

## 适用范围

- 仅用于 DNA 存储方向、且以实验结果为主的论文。
- 当前不覆盖偏理论论文（后续再单独添加理论版模板）。

## 阅读模式

- `略读`：1-2 页，快速建立论文全貌。
- `精读`：不少于10 页，完整展开方法、实验、图表与结论。
- 未明确指定时，默认使用 `精读`。

## 全局要求

1. 所有关键结论都要有证据（原文摘录 + 页码/章节/图表）。
2. 证据等级只使用：`原文支持`、`原文推理得到`、`原文未给或未找到`。
3. 图片引用优先使用相对路径（来自 `image_gallery.md`）。
4. 证据不足时明确写“当前证据不足”，不要补脑。
5. 标题后直接进入正文，不添加说明性引导语（例如“面向……结构化精读笔记”）。
6. 禁止使用“见下/如下”等占位衔接词，直接写具体内容。
7. 每条关键判断/结论后使用脚注引用证据，脚注编号统一使用 `[^章节-序号]`（例如 `[^1-1]`、`[^7-3]`）。
8. 区分“提示”与“正文”：提示规则只来自 `references/*.prompt.md` 与 `references/report-output-boundary.md`，提示文本不得写进最终报告。
9. 最终报告不得保留任何占位符（如 `<复制原文>`、`images/your-figure.png`）或选择提示（如 `[A | B]`）。
10. 精读报告优先使用“结论 + 脚注引用 + 映射矩阵”方式组织证据；证据三元组统一放在脚注定义中。
11. 条目级缺失/不适用：对 checkbox 枚举项保持未勾选即可；对开放项 `其它：` 若无具体内容直接删除该行（禁止写 `其它：本文不涉及`）；其余必须保留的字段缺失时写 `本文不涉及`（必要时说明影响），脚注证据等级可用 `原文未给或未找到` 记录检索结果。
12. 默认按模板章节与顺序输出；允许省略整体不适用的二级章节（`##`）；其余不得改写/合并/拆分/重排结构，也不新增二级章节。
13. 证据脚注定义统一集中放在文末“证据脚注”总章（避免打断阅读）：精读 `## 15 证据脚注`；略读 `## 9 证据脚注`。
14. 每条脚注定义必须包含三元组：`证据等级`、`证据原文摘录`、`来源位置`。
15. 正文中不写 `证据脚注：` 字段名，使用自然叙述并在句末添加脚注引用。
16. 精读报告必须包含 `## 14 复盘评分与发表定位`，对创新性/叙事性/复现性给出“评分 + 文字论证”，并补充“论文实际发表 + 发表定位（档位判断与依据）+ 为什么能发表在该期刊/会议 + 可发表性推演”（以上判断句末加脚注引用）。若论文为预印本（如 arXiv/bioRxiv），则不要求给出“发表档位判断/为什么能发表在该期刊或会议”两条，可只保留“可发表性推演”。

## 标准流程（必须）

建议显式指定 `--output-dir` 到 `codex论文阅读` 工作区根目录，不要使用 `artifacts` 目录作为输出根目录。

建议将临时报告（如 `/tmp/final_report.md`）放在 artifact 目录之外，并在写入 `summary_file` 后删除，避免重复文件。

```bash
bash scripts/setup_paper_env.sh paper

conda run -n paper python scripts/extract_paper_artifacts.py \
  "/absolute/path/to/paper.pdf" \
  --bundle-name "<论文目录名或简称（可选）>" \
  --output-dir "/absolute/path/to/codex论文阅读" \
  --summary-mode 精读 \
  --summary-init none \
  --layout bundle \
  --clean

conda run -n paper python scripts/write_final_report.py \
  --artifact-dir "/absolute/path/to/codex论文阅读/<论文目录名或简称>" \
  --input-file "/tmp/final_report.md"

conda run -n paper python scripts/check_report_not_template.py \
  --artifact-dir "/absolute/path/to/codex论文阅读/<论文目录名或简称>"

conda run -n paper python scripts/cleanup_artifacts.py \
  --target-dir "/absolute/path/to/codex论文阅读/<论文目录名或简称>" \
  --final-md-only \
  --report-name auto \
  --keep-file "image_gallery.md"
```

## 模式说明

### 略读模式

1. 快速说明论文要解决的问题。
2. 提炼 2-4 个核心创新点。
3. 简述 DNA 信道设定与关键实验。
4. 给出是否有代码/数据资源。
5. 先读 `references/dna-short-template.prompt.md`（带提示词模板）并按其章节执行；`assets/dna-short-template.md` 为自动生成的无提示词版本，用于覆盖检查；最后按 `references/report-output-boundary.md` 自检。

### 精读模式

1. 详细说明问题背景、方法流程与边界。
2. 重点拆开“仿真实验设计”和“湿实验设计”。
3. 逐条解读关键图表并对应到核心结论。
4. 结尾补充“延伸思考 + 复盘评分与发表定位（创新性/叙事性/复现性 + 发表定位推演）+ 不确定性声明”。
5. 先读 `references/dna-deep-template.prompt.md`（带提示词模板）并按其章节执行；`assets/dna-deep-template.md` 为自动生成的无提示词版本，用于覆盖检查；并执行 `references/dna-deep-checklist.md` + `references/report-output-boundary.md` 自检。

## 模板维护（单一源）

1. 将 `references/dna-short-template.prompt.md` 与 `references/dna-deep-template.prompt.md` 作为模板唯一来源。
2. 编辑提示模板后，运行 `python scripts/sync_output_templates.py` 自动生成 `assets/dna-short-template.md` 与 `assets/dna-deep-template.md`。
3. 交付前可运行 `python scripts/sync_output_templates.py --check` 检查是否已同步。
4. 原则上不要手动编辑 `assets/*.md`，避免与提示模板漂移。

## 文件交付要求（必须）

1. 从 `metadata.json` 读取 `summary_file` 作为最终交付路径。
2. 最终内容必须写入 `summary_file`，不能只在对话里输出。
3. 交付前必须运行 `check_report_not_template.py`。
4. 若校验失败，继续补全并重写，直到通过。

## 参考文件

- `assets/dna-short-template.md`：DNA 实验论文“略读”输出模板（无提示词）。
- `assets/dna-deep-template.md`：DNA 实验论文“精读”输出模板（无提示词）。
- `references/dna-short-template.prompt.md`：略读提示词模板（仅供模型参考，不直接输出）。
- `references/dna-deep-template.prompt.md`：精读提示词模板（仅供模型参考，不直接输出）。
- `references/report-output-boundary.md`：提示文本与最终正文的边界规则。
- `references/dna-deep-checklist.md`：精读模式检查清单。
- `references/paper-env-and-deps.md`：环境、命令与流程说明。
- `scripts/extract_paper_artifacts.py`：提取文本、图、表、链接等信息。
- `scripts/write_final_report.py`：写入最终报告到 `summary_file`。
- `scripts/check_report_not_template.py`：检查报告是否仍是模板内容。
- `scripts/sync_output_templates.py`：由提示模板自动生成无提示词模板。
- `scripts/cleanup_artifacts.py`：清理中间产物。
- `scripts/setup_paper_env.sh`：安装依赖。
