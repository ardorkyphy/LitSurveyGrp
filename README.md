# LitSurveyGrp

Open literature survey automation for research discovery.

LitSurveyGrp helps researchers discover papers, enrich scholarly metadata,
group papers into research topics, analyze cited references, collect selected
accessible PDFs, and generate research-oriented statistics and offline
dashboards.

The default workflow is metadata-first. It quickly collects candidate papers,
classifies and ranks them, then lets you download or analyze only the most
valuable papers.

## Quick Start

Install in editable mode from the project root:

```powershell
python -m pip install -e .
```

For development and PDF/reference extraction support:

```powershell
python -m pip install -r requirements-dev.txt
```

After installation, use the short command:

```powershell
lsg --help
lsg list-journals
```

The module entry point is also available during local development:

```powershell
python -m litsurveygrp --help
```

Optional API configuration can be provided through environment variables. Copy
`.env.example` to `.env` for local use, and never commit `.env`.

## Common Workflows

Minimal metadata-first run:

```powershell
lsg run-survey `
  --journal nature-aging `
  --per-journal-limit 10 `
  --papers-dir papers `
  --results-dir results
```

`run-survey` does not download PDFs by default. It writes metadata, topic
classification, statistics, and visualization first.

Run a Nature Aging survey:

```powershell
lsg run-survey `
  --journal nature-aging `
  --limit 50 `
  --papers-dir papers `
  --results-dir results `
  --analyze-references
```

For larger surveys, prefer limiting discovered records instead of requiring a
large number of completed PDFs:

```powershell
lsg run-survey `
  --journal nature-aging `
  --per-journal-limit 150 `
  --papers-dir papers `
  --results-dir results
```

PDF download is optional and slower. Use `--download-pdfs` explicitly only when
you want the discovery pipeline itself to try PDF acquisition. For larger
surveys, prefer the staged `download-pdfs` command below.

Download only the highest-value PDFs after a metadata-first run:

```powershell
lsg download-pdfs `
  --manifest results\classified_manifest.json `
  --papers-dir papers `
  --results-dir results `
  --top 20 `
  --download-workers 4
```

This command ranks papers by research value before downloading. The score uses
citation count, journal tier, recency, review-entry value, classification
confidence, and metadata completeness. Change `--top` to control how many PDFs
to attempt. Optional controls include `--min-value-score`, `--require-doi`, and
`--include-existing`.

Run a keyword-based survey:

```powershell
lsg run-survey `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30 `
  --papers-dir papers `
  --results-dir results
```

Repeat runs reuse cached OpenAlex pages from `results/metadata_cache` by
default. Override the cache location with `--metadata-cache-dir`, or disable it
with `--no-metadata-cache`.

Prepare the top papers for LLM research agents:

```powershell
lsg prepare-agent-input `
  --manifest results\classified_manifest.json `
  --out-dir agent_inputs\demo `
  --project-name demo `
  --top-domains 10 `
  --per-domain 30
```

Clean generated experiment outputs:

```powershell
lsg clean-results --target papers --target results
```

## Outputs

Typical output layout:

```text
papers/
  all_papers/
  Topic_.../

results/
  article_manifest.json
  enriched_manifest.json
  classified_manifest.json
  metadata_cache/
  pdf_download_ranking.csv
  pdf_downloaded_manifest.json
  pdf_download_report.csv
  pdf_download_summary.json
  download_report.csv
  run_monitor.html
  run_status.json
  pipeline_report.json
  stats/
  visualization/
  references/
```

Important files:

- `classified_manifest.json`: final paper metadata after enrichment and topic
  classification.
- `metadata_cache/`: cached metadata API pages for faster repeated runs.
- `stats/research_profile.json`: compact research profile for dashboard use.
- `stats/topic_profiles.csv`: topic distribution, representative papers, and
  topic trends.
- `stats/paper_recommendations.csv`: high-value source papers for reading.
- `pdf_download_ranking.csv`: ranked PDF-download candidates and reasons.
- `pdf_downloaded_manifest.json`: manifest after top-ranked PDF download.
- `references/reference_manifest.json`: ranked cited-reference paper pool.
- `run_monitor.html`: auto-refreshing run monitor for long jobs.
- `run_status.json`: machine-readable current stage, progress, last item, and
  recent events.

The main dashboard is:

```text
results/visualization/research_dashboard.html
```

During long runs, open this file in a browser to see what the tool is doing:

```text
results/run_monitor.html
```

It refreshes automatically and shows the active stage, processed record count,
last paper, current provider/API source, and recent errors or warnings.

You can also open or watch it from the CLI:

```powershell
lsg monitor --results-dir results --open
lsg monitor --results-dir results --watch
```

## Notes

- PDF acquisition is best-effort and depends on open-access availability,
  publisher behavior, and network conditions.
- Citation counts come from open sources such as OpenAlex and Crossref, so they
  may differ from Google Scholar, Web of Science, or Scopus.
- The project is a research-assistance tool, not a formal bibliometric
  evaluation system.
- LitSurveyGrp uses open APIs and accessible full-text sources. It is not
  intended to bypass paywalls or publisher access controls.

See also:

- `FAQ.md`
- `CONTRIBUTING.md`

## Pre-Release Checklist

Before publishing or tagging a release:

```powershell
python -m pytest tests -q
git status --short
```

Confirm that `.env`, `papers/`, `results/`, `agent_inputs/`, PDFs, model
caches, and other local experiment outputs are not staged.

## 中文简介

LitSurveyGrp 是一个面向科研调研的自动化工具，用于批量发现论文、补全开放学术元数据、
获取可访问 PDF、自动归组研究主题、分析引用文献，并生成科研统计和离线可视化报告。

安装后推荐使用短命令：

```powershell
lsg --help
```

开发和 PDF/引用提取相关依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

默认流程是 metadata-first：先快速生成候选论文元数据、权威 topic 分类、统计和可视化。
需要 PDF 时再显式使用 `--download-pdfs`，并可配合 `--download-workers`
并发下载可访问 PDF。

推荐的大规模流程是：先只获取元数据并完成分类统计，再按研究价值下载 Top PDF：

```powershell
lsg download-pdfs `
  --manifest results\classified_manifest.json `
  --papers-dir papers `
  --results-dir results `
  --top 20 `
  --download-workers 4
```

`--top` 就是“值得下载 PDF 的前几篇”这个超参。排序依据包括引用量、期刊水平、年份新近度、是否适合作为综述入口、分类置信度和元数据完整度。

说明：

- PDF 获取是开放全文优先、尽力而为，不保证每篇论文都能下载。
- 引用量来自 OpenAlex、Crossref 等开放来源，和 Google Scholar、Web of
  Science、Scopus 可能不同。
- 本项目用于辅助科研调研，不是正式文献计量评价系统。
- 项目不会绕过付费墙或出版社访问控制。
