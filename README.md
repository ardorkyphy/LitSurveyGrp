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
lsg survey `
  --out aging_demo `
  --journal nature-aging `
  --per-journal-limit 10 `
  --preset metadata `
  --skip-agents
```

This writes metadata, topic classification, statistics, and visualization under
`aging_demo`. Set `--preset metadata` when you want to skip PDF download and
agent interpretation.

Run a Nature Aging survey:

```powershell
lsg survey `
  --out nature_aging `
  --journal nature-aging `
  --limit 50 `
  --analyze-references
```

For larger surveys, prefer limiting discovered records instead of requiring a
large number of completed PDFs:

```powershell
lsg survey `
  --out nature_aging_large `
  --journal nature-aging `
  --per-journal-limit 150 `
  --skip-agents
```

PDF download is optional and slower. The public `survey` command downloads only
the top-ranked papers; use `--preset metadata` or `--pdfs 0` to skip that stage.

Download only the highest-value PDFs during a survey run:

```powershell
lsg survey `
  --out aging_top_pdfs `
  --journal nature-aging `
  --per-journal-limit 150 `
  --pdfs 20 `
  --download-workers 8
```

The survey ranks papers by research value before downloading. The score uses
citation count, journal tier, recency, review-entry value, classification
confidence, and metadata completeness. Change `--pdfs` to control how many
PDFs to attempt per selected domain. Optional internal controls include
`--min-value-score` and `--require-doi`.

Run a keyword-based survey:

```powershell
lsg survey `
  --out causal_discovery `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30
```

Repeat runs reuse cached OpenAlex pages from the run's `results/metadata_cache`
directory by default.

Prepare the top papers for LLM research agents as part of the survey:

```powershell
lsg survey `
  --out agent_demo `
  --query "Large Language Model causal discovery" `
  --preset full `
  --pdfs 20 `
  --domains 10 `
  --papers-per-domain 30
```

Run selected stages manually when you want tighter control over an existing
manifest:

```powershell
lsg enrich-metadata --manifest reports\<major_domain>\data\article_manifest.json --out reports\<major_domain>\data\enriched_manifest.json
lsg classify-papers --manifest reports\<major_domain>\data\enriched_manifest.json --out-dir reports\<major_domain>\data --organize-dir papers
lsg stats --manifest reports\<major_domain>\data\classified_manifest.json --out-dir reports\<major_domain>\data\stats
lsg visualize --manifest reports\<major_domain>\data\classified_manifest.json --out-dir reports\<major_domain>\data\visualization
lsg download-pdfs --manifest reports\<major_domain>\data\classified_manifest.json --papers-dir papers --results-dir reports\<major_domain>\data --top 20
lsg prepare-agent-input --manifest reports\<major_domain>\data\pdf_downloaded_manifest.json --out-dir results\<major_domain> --papers-dir papers --results-dir results --reports-dir reports --selection top-downloaded-pdfs --top-papers 30
```

These staged commands are intended for internal debugging and advanced
parameter tuning. For normal use, prefer `lsg survey`.

Run the full workflow with DeepSeek-backed agents:

First configure `DEEPSEEK_API_KEY` in your local environment or `.env`.

```powershell
python -m litsurveygrp survey `
  --out quantum_for_ai `
  --query "Quantum for AI" `
  --limit 1000 `
  --domains 3 `
  --papers-per-domain 5 `
  --model-provider deepseek `
  --workers 3 `
  --agent-input-mode evidence-chunks `
  --agent-max-chunks-per-paper 12 `
  --agent-max-chunk-chars 2200 `
  --agent-cache-dir quantum_for_ai\agent_cache
```

DeepSeek uses `DEEPSEEK_API_KEY` and defaults to `https://api.deepseek.com`
with model `deepseek-v4-flash`. You can override the endpoint or model with
`--agent-base-url` and `--agent-model`. The default provider remains
`dry-run`, so LLM calls only happen when you explicitly select an API provider.
The paper agent defaults to `--agent-input-mode evidence-chunks`: downloaded
PDFs are extracted as full text, local code splits the text into section-aware
chunks, and only the most relevant chunks are sent to the LLM. This keeps token
costs lower without relying on a blind prefix truncation. Use
`--max-text-chars 0` to keep full extracted text, which is the survey default;
set a positive value only when you explicitly want to cap local text storage.
Use `--agent-workers` conservatively for API-backed runs; `2` or `3` is a
reasonable starting point.

Local retrieval models can be stored under `agents/models/` for PDF evidence
chunk selection. The recommended first deployment is the embedding model only:

```powershell
python -m agents.local_models download --endpoint https://hf-mirror.com --no-reranker
python -m agents.local_models self-test --no-reranker
```

The self-test should report `device: cuda` and an embedding dimension of `1024`
on an NVIDIA GPU. The optional reranker model can be added later by running the
same download command without `--no-reranker`.

Agent outputs are schema-validated before they become report inputs. Paper
evidence snippets must be grounded in the supplied abstract, extracted text, or
selected evidence chunks. Final reports include an evidence trace table for
domain claims, linking claims to paper IDs/titles, evidence chunk IDs, sections,
and supporting snippets when available. Invalid outputs are written as
`*.error.json` and excluded from final reports.

Clean generated experiment outputs:

```powershell
lsg clean --target papers --target results
```

## Outputs

Typical output layout:

```text
papers/
  <major_domain>/
    <subdomain>/

results/
  <major_domain>/
    <subdomain>/

reports/
  <major_domain>/
    data/
      article_manifest.json
      enriched_manifest.json
      classified_manifest.json
      metadata_cache/
      pdf_downloaded_manifest.json
      pipeline_report.json
      run_monitor.html
      run_status.json
      download_report.csv
      pdf_download_ranking.csv
      pdf_download_report.csv
      pdf_download_summary.json
      stats/
      visualization/
      references/
        reference_manifest.json
        reference_candidates.csv
        reference_summary.json
    <subdomain>/
      domain_report.md
      final_survey_report.md
      final_survey_report.html
```

Important files:

- `reports/<major_domain>/data/classified_manifest.json`: final paper metadata after enrichment and topic
  classification.
- `reports/<major_domain>/data/metadata_cache/`: cached metadata API pages for faster repeated runs.
- `reports/<major_domain>/data/stats/research_profile.json`: compact research profile for dashboard use.
- `reports/<major_domain>/data/stats/topic_profiles.csv`: topic distribution, representative papers, and
  topic trends.
- `reports/<major_domain>/data/stats/paper_recommendations.csv`: high-value source papers for reading.
- `reports/<major_domain>/data/pdf_download_ranking.csv`: ranked PDF-download candidates and reasons.
- `reports/<major_domain>/data/pdf_downloaded_manifest.json`: manifest after top-ranked PDF download.
- `reports/<major_domain>/data/references/reference_manifest.json`: ranked cited-reference paper pool.
- `reports/<major_domain>/data/run_monitor.html`: auto-refreshing run monitor for long jobs.
- `reports/<major_domain>/data/run_status.json`: machine-readable current stage, progress, last item, and
  recent events.

The main dashboard is:

```text
reports/<major_domain>/data/visualization/research_dashboard.html
```

During long runs, open this file in a browser to see what the tool is doing:

```text
reports/<major_domain>/data/run_monitor.html
```

It refreshes automatically and uses one HTML file for the whole workflow,
including metadata collection, PDF download, agent input preparation, paper
reading, domain synthesis, and final report generation. It shows the active
stage, processed record count, current item, provider/API source, and recent
errors or warnings.

You can also open or watch it from the CLI:

```powershell
lsg monitor --dir reports/<major_domain>/data --open
lsg monitor --dir reports/<major_domain>/data --watch
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

Confirm that `.env`, `papers/`, `results/`, `reports/`, PDFs, model
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

默认流程先快速生成候选论文元数据、权威 topic 分类、统计和可视化。
需要 PDF 时使用 `survey` 的 `--pdfs` 控制每个入选领域下载多少篇 PDF，
并可配合 `--download-workers` 并发下载可访问 PDF。默认 PDF 下载并发为 8。
常用预设是 `--preset fast|balanced|full|metadata`。

推荐的大规模流程是：限制候选元数据规模，再按研究价值下载 Top PDF：

```powershell
lsg survey `
  --out large_survey `
  --journal nature-aging `
  --per-journal-limit 150 `
  --pdfs 20 `
  --download-workers 8
```

`--top` 就是“值得下载 PDF 的前几篇”这个超参。排序依据包括引用量、期刊水平、年份新近度、是否适合作为综述入口、分类置信度和元数据完整度。

说明：

- PDF 获取是开放全文优先、尽力而为，不保证每篇论文都能下载。
- 引用量来自 OpenAlex、Crossref 等开放来源，和 Google Scholar、Web of
  Science、Scopus 可能不同。
- 本项目用于辅助科研调研，不是正式文献计量评价系统。
- 项目不会绕过付费墙或出版社访问控制。
