# LitSurveyGrp

LitSurveyGrp is a local literature-survey automation tool. It is designed for
research exploration rather than simple paper downloading: it discovers papers,
enriches metadata, classifies papers into research topics, downloads selected
open-access PDFs when requested, extracts references, writes research-oriented
statistics, and generates an offline dashboard.

The current project name is inherited from an earlier downloader prototype, but
the current codebase is a survey pipeline for academic literature analysis.

## What It Does

- Discovers papers from Nature-family pages, OpenAlex, Crossref, and layered
  journal providers.
- Supports multi-journal and keyword-based discovery.
- Applies optional filters before download:
  - required keywords
  - article type
  - citation threshold
  - year or year range
  - author
  - institution
- Enriches metadata through open scholarly APIs, mainly OpenAlex, Europe PMC,
  Crossref, and optional Semantic Scholar.
- Resolves PDFs through provider URLs and open-access sources such as PMC,
  Europe PMC, Unpaywall, CORE, PLOS, MDPI, and publisher links when available.
- Classifies papers automatically with SPECTER-style semantic embeddings and
  clustering. Topic labels are generated from the papers instead of being
  manually specified by the user.
- Extracts and ranks cited-reference papers.
- Produces research-facing statistics and visualization:
  - research topic distribution
  - yearly trends
  - author, institution, and team statistics
  - journal and article-type distribution
  - key paper recommendations
  - cited-reference insights
  - offline HTML dashboard

## Installation

Run commands from the project root:

```powershell
cd D:\lky\school\science\AI医疗\自动化工具
python -m pip install -r requirements.txt
```

If optional NLP dependencies are not installed, classification may fall back or
be less capable. For semantic clustering, install the SPECTER-related
dependencies used by the project:

```powershell
python -m pip install sentence-transformers scikit-learn
```

The project supports Chinese paths. Generated files are intended to be written
under local `papers/`, `results/`, and `reports/` directories or user-specified
output directories.

## Common Commands

After installation, use the short CLI name `lsg`. During local development,
`python -m litsurveygrp` runs the same command interface.

Fetch PDFs directly from a title or keyword query:

```powershell
lsg fetch-pdf `
  --out paper_fetch `
  --title "The Hallmarks of Aging" `
  --limit 5 `
  --top 1
```

```powershell
lsg fetch-pdf `
  --out senescence_pdf_fetch `
  --query "cellular senescence aging intervention" `
  --limit 20 `
  --top 5
```

Analyze one local PDF as a single-paper report:

```powershell
lsg analyze-pdf `
  --pdf papers\paper.pdf `
  --out single_paper_report `
  --title "Paper title" `
  --model-provider deepseek `
  --agent-cache-dir single_paper_report\agent_cache
```

`analyze-pdf` defaults to full-text agent input so it can run without local
retrieval models. Switch to `--agent-input-mode evidence-chunks` after deploying
the optional local embedding/reranker models.

List built-in journal sources:

```powershell
lsg list-journals
```

Run a full Nature Aging survey:

```powershell
lsg survey `
  --out nature_aging `
  --journal nature-aging `
  --limit 50 `
  --download-workers 8 `
  --analyze-references
```

For larger surveys, prefer limiting discovered records with
`--per-journal-limit`. This produces metadata, classification, statistics, and
visualization faster:

```powershell
lsg survey `
  --out nature_aging_large `
  --journal nature-aging `
  --per-journal-limit 150 `
  --preset metadata `
  --skip-agents
```

PDF download is optional and slower. The public `survey` command downloads only
the top-ranked papers; use `--preset metadata` or `--pdfs 0` to skip that stage.

Download PDFs later by top research value:

```powershell
lsg download-pdfs `
  --manifest reports\<大领域>\data\classified_manifest.json `
  --papers-dir papers `
  --results-dir reports\<大领域>\data `
  --top 20 `
  --download-workers 8
```

This separate PDF stage ranks the manifest first and then attempts only the
top papers. The ranking score combines citation count, journal tier, recency,
review-entry value, classification confidence, and metadata completeness. The
main hyperparameter is `--top`; users can also add `--min-value-score`,
`--require-doi`, or `--include-existing`.

Repeat runs reuse cached OpenAlex pages from `reports/<大领域>/data/metadata_cache` by
default.

Prepare top papers for LLM research agents:

```powershell
lsg prepare-agent-input `
  --manifest reports\<大领域>\data\pdf_downloaded_manifest.json `
  --out-dir results\<大领域> `
  --papers-dir papers `
  --results-dir results `
  --reports-dir reports `
  --project-name demo `
  --selection top-downloaded-pdfs `
  --pdfs 30 `
  --max-text-chars 0
```

The survey command now keeps extracted PDF text by default
(`--max-text-chars 0`) and controls LLM cost at the agent layer. The paper
agent defaults to `--agent-input-mode evidence-chunks`: local code splits full
text into section-aware chunks, selects the chunks most relevant to research
problem, methods, findings, and limitations, and sends only those chunks to the
LLM. For API-backed runs, start with conservative parallelism:

```powershell
lsg survey `
  --out agent_demo `
  --query "Large Language Model causal discovery" `
  --agent-provider deepseek `
  --agent-workers 3 `
  --agent-input-mode evidence-chunks `
  --agent-max-chunks-per-paper 12 `
  --agent-max-chunk-chars 2200 `
  --agent-cache-dir agent_demo\agent_cache
```

Final reports include an evidence trace table for domain-level claims. The
table links claims to paper IDs/titles, selected chunk IDs, chunk sections, and
supporting snippets when available. Invalid agent outputs are written as
`*.error.json` and excluded from final reports.

Local retrieval models can be stored under `agents/models/`. Start with the
embedding model:

```powershell
python -m agents.local_models download --endpoint https://hf-mirror.com --no-reranker
python -m agents.local_models self-test --no-reranker
```

The optional reranker can be downloaded later by omitting `--no-reranker`.

Run a keyword-based survey across journals:

```powershell
lsg survey `
  --out causal_discovery `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30 `
  --analyze-references
```

Filter by year, article type, or citation count:

```powershell
lsg survey `
  --out aging_filtered `
  --journal nature-aging `
  --from-year 2022 `
  --to-year 2026 `
  --article-type Article `
  --min-citations 10 `
  --limit 50
```

Clean generated experiment outputs:

```powershell
lsg clean --target papers --target results
```

Run individual steps:

```powershell
lsg enrich-metadata --manifest reports\<大领域>\data\article_manifest.json --out reports\<大领域>\data\enriched_manifest.json
lsg classify-papers --manifest reports\<大领域>\data\enriched_manifest.json --out-dir reports\<大领域>\data --organize-dir papers
lsg stats --manifest reports\<大领域>\data\classified_manifest.json --out-dir reports\<大领域>\data\stats
lsg visualize --manifest reports\<大领域>\data\classified_manifest.json --out-dir reports\<大领域>\data\visualization
lsg download-pdfs --manifest reports\<大领域>\data\classified_manifest.json --papers-dir papers --results-dir reports\<大领域>\data --top 20
lsg prepare-agent-input --manifest reports\<大领域>\data\pdf_downloaded_manifest.json --out-dir results\<大领域> --papers-dir papers --results-dir results --reports-dir reports --selection top-downloaded-pdfs --top-papers 30
```

These staged commands are intended for internal debugging and advanced
parameter tuning. For normal use, prefer `lsg survey`.

## Output Layout

Typical full-pipeline outputs:

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
        research_dashboard.html
      references/
        reference_manifest.json
        reference_candidates.csv
        reference_summary.json
    <subdomain>/
      domain_report.md
      final_survey_report.md
      final_survey_report.html
```

The main dashboard is:

```text
reports/<大领域>/data/visualization/research_dashboard.html
```

The live monitor is one auto-refreshing HTML file for the whole workflow:

```text
reports/<大领域>/data/run_monitor.html
```

It tracks metadata collection, PDF download, agent input preparation, paper
reading, domain synthesis, and final report generation in the same page.

## Tasks Already Tried

The project has already been exercised on several realistic tasks:

- Nature Aging issue/journal crawling with PDF download.
- Larger Nature Aging runs with pagination fixes.
- Multi-journal discovery through layered OpenAlex, Crossref, and publisher
  crawling.
- Keyword-based discovery for topics such as large language models and causal
  discovery.
- Metadata enrichment, especially citation counts through OpenAlex and fallback
  sources.
- SPECTER-based automatic topic clustering.
- Folder organization of downloaded PDFs by discovered topic.
- Reference extraction, reference-paper enrichment, relevance scoring, and
  value ranking.
- Research statistics and offline dashboard generation.

## Strengths

- Uses open scholarly infrastructure first, which is more stable than scraping
  Google Scholar.
- Supports multi-source fallback for metadata and PDFs.
- Keeps PDF acquisition separate from metadata collection, so useful survey
  statistics can still be produced even when PDFs are unavailable.
- Can rank papers by research value and download only the top PDFs selected by
  the user.
- Automatically clusters papers into topics rather than requiring manually
  defined field labels.
- Produces research-facing outputs instead of only operational download logs.
- Handles Chinese filesystem paths.
- Keeps generated experiment outputs separate from source code.
- Has unit tests for the main contracts; the current suite covers downloader,
  metadata, classification, filtering, statistics, visualization, reference
  analysis, and CLI behavior.

## Current Limitations

- PDF availability is inherently uneven. Some publishers return 403 responses
  or do not expose open PDFs even when metadata is available.
- Citation counts are not identical across sources. OpenAlex is used as a main
  practical source, while Crossref and other sources are fallbacks with uneven
  coverage.
- Semantic Scholar is optional because API access and privacy requirements may
  not be suitable for every user.
- SPECTER clustering quality depends on title/abstract quality and available
  model files. Weak metadata can produce weak topic labels.
- Reference extraction from PDFs is heuristic. It works for many normal papers
  but can fail on unusual layouts, scanned PDFs, or incomplete downloads.
- Journal-tier scoring uses a conservative local map. It is useful for ranking
  but is not a substitute for a formal bibliometric database.
- Real network runs are affected by publisher limits, API limits, regional
  availability, and temporary service failures.

## API Rate Use

The pipeline exposes `--request-interval` for metadata APIs. Use a conservative
interval when running large jobs. A practical default is to keep API requests
spaced rather than hammering services. For large real experiments, prefer:

```powershell
--request-interval 1.0
```

or higher if a provider asks for slower access. Publisher crawling and PDF
download behavior should also remain conservative.

## English / Chinese

# LitSurveyGrp 中文说明

LitSurveyGrp 是一个本地运行的学术调研自动化工具。它的目标不是单纯批量下载论文，而是围绕某个科研问题或期刊集合，自动完成论文发现、元数据补全、PDF 获取、引用论文挖掘、语义聚类、科研统计和可视化。

当前项目名沿用了早期下载器原型的名字，但现在的代码已经转向“文献调研流水线”。

## 项目能做什么

- 从 Nature 系列网页、OpenAlex、Crossref 和分层期刊源中发现论文。
- 支持多期刊抓取和关键词检索。
- 支持下载前筛选：
  - 关键词
  - 文章类型
  - 引用量阈值
  - 年份或年份范围
  - 作者
  - 机构
- 通过开放学术 API 补全元数据，主要包括 OpenAlex、Europe PMC、Crossref，以及可选 Semantic Scholar。
- 通过开放全文来源解析 PDF，包括 PMC、Europe PMC、Unpaywall、CORE、PLOS、MDPI 和可访问的出版社直链。
- 使用 SPECTER 语义嵌入进行自动聚类，领域标签从论文标题、摘要和文本中自动生成，不需要用户手动指定模板。
- 提取引用文献，并对引用论文做相关性和价值排序。
- 输出科研人员更关心的统计和图表：
  - 研究子领域分布
  - 年份趋势
  - 高影响作者、机构、团队
  - 期刊和文章类型分布
  - 关键论文推荐
  - 核心引用文献
  - 离线 HTML dashboard

## 使用方法

安装后推荐使用短命令 `lsg`。在本地开发目录中，也可以用
`python -m litsurveygrp` 调用同一套命令行入口。

在项目根目录运行：

```powershell
cd D:\lky\school\science\AI医疗\自动化工具
lsg list-journals
```

完整运行 Nature Aging 调研：

```powershell
lsg survey `
  --out nature_aging `
  --journal nature-aging `
  --limit 50 `
  --download-workers 8 `
  --analyze-references
```

大规模实验建议用 `--per-journal-limit` 控制“抓取多少篇文章记录”，而不是用很大的
`--limit` 要求完成大量 PDF。这样可以更快得到元数据、分类、统计和图表：

```powershell
lsg survey `
  --out nature_aging_large `
  --journal nature-aging `
  --per-journal-limit 150 `
  --top-papers 0 `
  --skip-agents
```

PDF 下载是可选项且速度较慢。`survey` 默认只尝试下载排名靠前的论文；
使用 `--preset metadata` 或 `--pdfs 0` 可以跳过这个阶段，也可以配合
`--download-workers` 并发下载。默认 PDF 下载并发为 8。

Agent 分析默认采用 `evidence-chunks` 模式：PDF 文本会完整抽取并保存在本地
（`--max-text-chars 0` 表示不截断），随后本地按章节切块并筛选与研究问题、
方法、发现、局限最相关的证据块，再把这些证据块送入 LLM。这样不会简单截取
论文开头，也能控制 token 成本。API 模型建议先用 `--agent-workers 2` 或
`--agent-workers 3`，并配合 `--agent-cache-dir` 复用重复运行的结果。

最终报告会为领域级结论补充 evidence trace 表，把 claim 关联到 paper id/标题、
chunk id、章节和 supporting snippet；验证失败的 agent 输出会写入
`*.error.json`，不会进入最终报告。

也可以先完整跑完元数据、分类、统计和可视化，再按研究价值排序下载最值得看的 PDF：

```powershell
lsg download-pdfs `
  --manifest reports\<大领域>\data\classified_manifest.json `
  --papers-dir papers `
  --results-dir reports\<大领域>\data `
  --top 20 `
  --download-workers 8
```

这里的 `--top` 是“下载排名前几篇 PDF”的超参。排序综合考虑引用量、期刊水平、年份新近度、综述入口价值、分类置信度和元数据完整度。还可以使用 `--min-value-score`、`--require-doi`、`--include-existing` 控制候选范围。

按关键词跨期刊检索：

```powershell
lsg survey `
  --out causal_discovery `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30 `
  --analyze-references
```

清理历史实验输出：

```powershell
lsg clean --target papers --target results
```

## 输出结果

完整流程固定使用 `papers/`、`results/`、`reports/` 三个根目录：PDF 保存在 `papers/<大领域>/<小领域>/`，agent 输入与分析中间产物保存在 `results/<大领域>/<小领域>/`，元数据、CSV、JSON、HTML、monitor 等调研记录保存在 `reports/<大领域>/data/`，小领域报告和总报告保存在 `reports/<大领域>/<小领域>/`。

最重要的结果文件包括：

- `reports/<大领域>/data/classified_manifest.json`
- `reports/<大领域>/data/stats/research_profile.json`
- `reports/<大领域>/data/stats/topic_profiles.csv`
- `reports/<大领域>/data/stats/paper_recommendations.csv`
- `reports/<大领域>/data/stats/reference_insights.csv`
- `reports/<大领域>/data/visualization/research_dashboard.html`
- `results/<大领域>/<小领域>/domain_synthesis.json`
- `reports/<大领域>/<小领域>/domain_report.md`
- `reports/<大领域>/<小领域>/final_survey_report.md`
- `reports/<大领域>/data/references/reference_manifest.json`
- `reports/<大领域>/data/pdf_download_ranking.csv`
- `reports/<大领域>/data/pdf_downloaded_manifest.json`

## 已经尝试过的任务

- Nature Aging 论文抓取和 PDF 下载。
- Nature Aging 翻页问题修复后的较大规模抓取。
- 多期刊分层抓取：OpenAlex 优先，Crossref 兜底，最后再尝试出版社网页。
- 按关键词检索，例如 LLM 与 causal discovery。
- 自动元数据增强和引用量补全。
- SPECTER 自动领域聚类。
- 按聚类领域整理 PDF 文件夹。
- 引用文献提取、补元数据、相关性判断和价值排序。
- 研究统计与离线可视化 dashboard。

## 项目优点

- 优先依赖开放学术数据源，比 Google Scholar 抓取类方案更适合稳定批量使用。
- 元数据和 PDF 下载分离，即使 PDF 不可得，也能保留论文元数据并完成统计。
- 可以按研究价值排序，只下载用户指定数量的 Top PDF。
- 支持多来源兜底，减少单一网站失败导致的整体失败。
- 自动生成研究领域标签，不需要用户预先设计分类模板。
- 输出面向科研调研，而不是只展示下载失败次数。
- 支持中文路径。
- 测试覆盖了下载、筛选、增强、分类、统计、可视化、引用分析和 CLI。

## 当前局限

- PDF 获取并不总是稳定，出版社 403、无开放全文、地区访问限制都会影响结果。
- 不同来源的引用量口径不同，OpenAlex、Crossref、Semantic Scholar 的数字可能不一致。
- Semantic Scholar 可选，不作为强依赖。
- SPECTER 聚类依赖标题和摘要质量，元数据差时聚类标签也会变差。
- PDF 引用提取是启发式方法，对扫描件、复杂排版或不完整 PDF 不一定可靠。
- 期刊水平 map 是本地保守规则，只适合辅助排序，不等同于正式文献计量评价。
- 真实网络实验会受到 API 限流、出版社限制和服务波动影响。

