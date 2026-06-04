# LitSurveyGrp

LitSurveyGrp is a local literature-survey automation tool. It is designed for
research exploration rather than simple paper downloading: it discovers papers,
enriches metadata, resolves open-access PDFs, extracts references, clusters
papers into research topics, writes research-oriented statistics, and generates
an offline dashboard.

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
under local `papers/` and `results/` directories or user-specified output
directories.

## Common Commands

After installation, use the short CLI name `lsg`. During local development,
`python -m litsurveygrp` runs the same command interface.

List built-in journal sources:

```powershell
lsg list-journals
```

Run a full Nature Aging survey:

```powershell
lsg run-survey `
  --journal nature-aging `
  --limit 50 `
  --download-workers 4 `
  --papers-dir papers `
  --results-dir results `
  --analyze-references
```

For larger surveys, prefer limiting discovered records with
`--per-journal-limit` instead of asking for a large number of completed PDFs.
This produces metadata, classification, statistics, and visualization faster
without coupling the run to PDF availability:

```powershell
lsg run-survey `
  --journal nature-aging `
  --per-journal-limit 150 `
  --metadata-only `
  --papers-dir papers `
  --results-dir results
```

PDF download is optional. By default LitSurveyGrp tries to download accessible
PDFs. Use `--metadata-only` when you want fast metadata, classification,
statistics, and visualization first. Use `--download-pdfs` explicitly when you
want the pipeline to try PDF acquisition, optionally with `--download-workers`.

Download PDFs later by top research value:

```powershell
lsg download-pdfs `
  --manifest results\classified_manifest.json `
  --papers-dir papers `
  --results-dir results `
  --top 20 `
  --download-workers 4
```

This separate PDF stage ranks the manifest first and then attempts only the
top papers. The ranking score combines citation count, journal tier, recency,
review-entry value, classification confidence, and metadata completeness. The
main hyperparameter is `--top`; users can also add `--min-value-score`,
`--require-doi`, or `--include-existing`.

Run a keyword-based survey across journals:

```powershell
lsg run-survey `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30 `
  --papers-dir papers `
  --results-dir results `
  --analyze-references
```

Filter by year, article type, citation count, author, or institution:

```powershell
lsg run-survey `
  --journal nature-aging `
  --from-year 2022 `
  --to-year 2026 `
  --article-type Article `
  --min-citations 10 `
  --author "Smith" `
  --institution "Harvard" `
  --limit 50 `
  --papers-dir papers `
  --results-dir results
```

Clean generated experiment outputs:

```powershell
lsg clean-results --target papers --target results
```

Run individual steps:

```powershell
lsg enrich-metadata --manifest results\article_manifest.json
lsg classify-papers --manifest results\enriched_manifest.json --out-dir results --organize-dir papers
lsg stats --manifest results\classified_manifest.json --out-dir results\stats
lsg visualize --manifest results\classified_manifest.json --out-dir results\visualization
lsg download-pdfs --manifest results\classified_manifest.json --papers-dir papers --results-dir results --top 20
lsg analyze-references --manifest results\classified_manifest.json --out-dir results\references
```

## Output Layout

Typical full-pipeline outputs:

```text
papers/
  all_papers/
  Topic_.../

results/
  article_manifest.json
  enriched_manifest.json
  classified_manifest.json
  download_report.csv
  pdf_download_ranking.csv
  pdf_downloaded_manifest.json
  pdf_download_report.csv
  pdf_download_summary.json
  pipeline_report.json
  stats/
    summary.json
    research_profile.json
    topic_profiles.csv
    paper_recommendations.csv
    reference_insights.csv
    author_stats.csv
    institution_stats.csv
    journal_stats.csv
    year_trend.csv
  visualization/
    research_dashboard.html
  references/
    reference_manifest.json
    reference_candidates.csv
    reference_summary.json
```

The main dashboard is:

```text
results/visualization/research_dashboard.html
```

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
lsg run-survey `
  --journal nature-aging `
  --limit 50 `
  --download-workers 4 `
  --papers-dir papers `
  --results-dir results `
  --analyze-references
```

大规模实验建议用 `--per-journal-limit` 控制“抓取多少篇文章记录”，而不是用很大的
`--limit` 要求完成大量 PDF。这样可以更快得到元数据、分类、统计和图表：

```powershell
lsg run-survey `
  --journal nature-aging `
  --per-journal-limit 150 `
  --metadata-only `
  --papers-dir papers `
  --results-dir results
```

PDF 下载是可选项。默认会尝试下载可访问 PDF；如果只想先快速获取数据和研究画像，
使用 `--metadata-only`。需要 PDF 时再显式使用 `--download-pdfs`，也可以配合
`--download-workers` 并发下载。

也可以先完整跑完元数据、分类、统计和可视化，再按研究价值排序下载最值得看的 PDF：

```powershell
lsg download-pdfs `
  --manifest results\classified_manifest.json `
  --papers-dir papers `
  --results-dir results `
  --top 20 `
  --download-workers 4
```

这里的 `--top` 是“下载排名前几篇 PDF”的超参。排序综合考虑引用量、期刊水平、年份新近度、综述入口价值、分类置信度和元数据完整度。还可以使用 `--min-value-score`、`--require-doi`、`--include-existing` 控制候选范围。

按关键词跨期刊检索：

```powershell
lsg run-survey `
  --query "Large Language Model causal discovery" `
  --keyword "Large Language Model" `
  --keyword "causal discovery" `
  --limit 30 `
  --papers-dir papers `
  --results-dir results `
  --analyze-references
```

清理历史实验输出：

```powershell
lsg clean-results --target papers --target results
```

## 输出结果

完整流程会在 `papers/` 中保存 PDF，并按自动聚类出来的领域整理文件夹；在 `results/` 中保存元数据、统计表格、引用文献分析和可视化 dashboard。

最重要的结果文件包括：

- `results/classified_manifest.json`
- `results/stats/research_profile.json`
- `results/stats/topic_profiles.csv`
- `results/stats/paper_recommendations.csv`
- `results/stats/reference_insights.csv`
- `results/visualization/research_dashboard.html`
- `results/references/reference_manifest.json`
- `results/pdf_download_ranking.csv`
- `results/pdf_downloaded_manifest.json`

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

