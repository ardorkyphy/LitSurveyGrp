# -*- coding: utf-8 -*-
"""Self-contained HTML visualizations for research survey manifests."""

import html
import json
from pathlib import Path

from litsurveygrp.research_stats import ResearchStatsWriter, top_rows_with_other


class ResearchDashboardWriter:
    """Generate an offline research dashboard from a manifest."""

    def __init__(self, manifest_path: Path, out_dir: Path | None = None, top_n: int = 15):
        self.manifest_path = Path(manifest_path)
        self.out_dir = Path(out_dir) if out_dir else self.manifest_path.parent / "visualization"
        self.top_n = top_n
        self.stats = ResearchStatsWriter(self.manifest_path, top_n=top_n)

    def write(self) -> Path:
        articles = self.stats.load_manifest()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "research_dashboard.html"
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.render(articles))
        return path

    def render(self, articles) -> str:
        summary = self.stats.summary(articles)
        profile = self.stats.research_profile(articles)
        all_subdomains = self.stats.subdomain_stats(articles)
        subdomains = top_rows_with_other(all_subdomains, self.top_n, "subdomain")
        topic_profiles = self.stats.topic_profiles(articles)[: self.top_n]
        years = self.stats.year_trend(articles)
        authors = self.stats.author_stats(articles)[: self.top_n]
        institutions = self.stats.institution_stats(articles)[: self.top_n]
        journals = self.stats.journal_stats(articles)[: self.top_n]
        article_types = self.stats.article_type_stats(articles)
        top_papers = self.stats.top_papers(articles)[: self.top_n]
        recommendations = self.stats.paper_recommendations(articles)[: self.top_n]
        references = self.stats.reference_insights(articles)[: self.top_n]
        data_json = html.escape(json.dumps({
            "summary": summary,
            "research_profile": profile,
            "subdomains": subdomains,
            "topic_profiles": topic_profiles,
            "years": years,
            "authors": authors,
            "institutions": institutions,
            "journals": journals,
            "article_types": article_types,
            "top_papers": top_papers,
            "paper_recommendations": recommendations,
            "reference_insights": references,
        }, ensure_ascii=False))
        return "\n".join([
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Research Dashboard</title>",
            f"<style>{self.styles()}</style>",
            "</head>",
            "<body>",
            "<main>",
            self.header(summary),
            self.metric_strip(summary),
            self.panel("研究画像摘要", self.profile_brief(profile), wide=True),
            '<section class="grid two">',
            self.panel(
                "研究子领域分布",
                self.covered_bar_chart(subdomains, summary.get("total_papers", 0), "subdomain", "paper_count", "citation_count"),
            ),
            self.panel("年份趋势", self.year_chart(years)),
            "</section>",
            self.panel("子领域档案", self.topic_profile_table(topic_profiles), wide=True),
            self.panel("推荐阅读路径", self.recommendation_table(recommendations), wide=True),
            '<section class="grid two">',
            self.panel("高影响作者", self.bar_chart(authors, "author", "paper_count", "citation_count")),
            self.panel("高影响机构", self.bar_chart(institutions, "institution", "paper_count", "citation_count")),
            "</section>",
            '<section class="grid two">',
            self.panel("期刊分布", self.bar_chart(journals, "journal", "paper_count", "citation_count")),
            self.panel("文章类型", self.bar_chart(article_types, "article_type", "paper_count", "citation_count")),
            "</section>",
            self.panel("关键论文", self.paper_table(top_papers), wide=True),
            self.panel("核心引用文献", self.reference_table(references), wide=True),
            f'<script id="dashboard-data" type="application/json">{data_json}</script>',
            "</main>",
            "</body>",
            "</html>",
        ])

    def header(self, summary: dict) -> str:
        year_range = " - ".join([value for value in [summary.get("year_min"), summary.get("year_max")] if value]) or "Unknown"
        return (
            '<header class="page-header">'
            '<div><p class="eyebrow">Literature Survey</p>'
            '<h1>Research Dashboard</h1></div>'
            f'<p class="range">Year range: {escape(year_range)}</p>'
            "</header>"
        )

    def metric_strip(self, summary: dict) -> str:
        metrics = [
            ("论文数", summary.get("total_papers", 0)),
            ("总引用", summary.get("total_citations", 0)),
            ("平均引用", summary.get("average_citations", 0)),
            ("中位引用", summary.get("median_citations", 0)),
            ("PDF覆盖率", f'{round(float(summary.get("open_fulltext_coverage", 0)) * 100, 1)}%'),
            ("作者数", summary.get("unique_authors", 0)),
            ("机构数", summary.get("unique_institutions", 0)),
        ]
        items = [
            f'<div class="metric"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
            for label, value in metrics
        ]
        return '<section class="metrics">' + "".join(items) + "</section>"

    def panel(self, title: str, content: str, wide: bool = False) -> str:
        class_name = "panel wide" if wide else "panel"
        return f'<section class="{class_name}"><h2>{escape(title)}</h2>{content}</section>'

    def profile_brief(self, profile: dict) -> str:
        overview = profile.get("overview", {})
        growing_topics = profile.get("growing_topics", [])[:3]
        classics = profile.get("classic_papers", [])[:3]
        recent = profile.get("recent_high_potential_papers", [])[:3]
        references = profile.get("core_references", [])[:3]
        blocks = [
            ("升温方向", [row.get("subdomain", "") for row in growing_topics]),
            ("经典入口", [row.get("title", "") for row in classics]),
            ("近年潜力论文", [row.get("title", "") for row in recent]),
            ("核心引用文献", [row.get("title", "") for row in references]),
        ]
        cards = []
        for title, values in blocks:
            items = values or ["暂无数据"]
            cards.append(
                '<div class="brief-card">'
                f'<h3>{escape(title)}</h3>'
                + "".join(f"<p>{escape(value)}</p>" for value in items[:3])
                + "</div>"
            )
        footer = (
            f'研究论文 {escape(overview.get("research_papers", 0))} 篇，'
            f'综述/综述入口 {escape(overview.get("review_papers", 0))} 篇，'
            f'引用文献池 {escape(overview.get("reference_pool_size", 0))} 条。'
        )
        return '<div class="brief-grid">' + "".join(cards) + f'</div><p class="brief-note">{footer}</p>'

    def bar_chart(self, rows: list[dict], label_key: str, count_key: str, citation_key: str) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        max_count = max(int(row.get(count_key) or 0) for row in rows) or 1
        items = []
        for row in rows:
            label = escape(row.get(label_key, "Unknown"))
            count = int(row.get(count_key) or 0)
            citations = int(row.get(citation_key) or 0)
            width = max(4, round(count / max_count * 100, 2))
            items.append(
                '<div class="bar-row">'
                f'<div class="bar-label" title="{label}">{label}</div>'
                '<div class="bar-track">'
                f'<div class="bar-fill" style="width:{width}%"></div>'
                "</div>"
                f'<div class="bar-value"><span>{count}篇</span><span>{citations}引</span></div>'
                "</div>"
            )
        return '<div class="bar-chart">' + "".join(items) + "</div>"

    def covered_bar_chart(self, rows: list[dict], total: int, label_key: str, count_key: str, citation_key: str) -> str:
        chart = self.bar_chart(rows, label_key, count_key, citation_key)
        shown = sum(int(row.get(count_key) or 0) for row in rows)
        note = f"当前图表覆盖 {shown}/{int(total or 0)} 篇；超过 Top {self.top_n} 的领域合并为其他领域。"
        return chart + f'<p class="chart-note">{escape(note)}</p>'

    def topic_profile_table(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        body = []
        for row in rows:
            body.append(
                "<tr>"
                f'<td>{escape(row.get("subdomain", ""))}</td>'
                f'<td class="number">{escape(row.get("paper_count", 0))}</td>'
                f'<td class="number">{escape(row.get("citation_count", 0))}</td>'
                f'<td>{escape(row.get("trend", ""))}</td>'
                f'<td>{escape(row.get("representative_keywords", ""))}</td>'
                f'<td class="paper-title">{escape(row.get("top_cited_papers", ""))}</td>'
                "</tr>"
            )
        return (
            '<div class="table-wrap"><table>'
            "<thead><tr><th>Topic</th><th>论文</th><th>引用</th><th>趋势</th><th>关键词</th><th>代表论文</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>"
        )

    def recommendation_table(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        body = []
        for row in rows:
            body.append(
                "<tr>"
                f'<td class="number">{escape(row.get("rank", ""))}</td>'
                f'<td>{escape(row.get("recommendation_type", ""))}</td>'
                f'<td class="paper-title">{escape(row.get("title", ""))}</td>'
                f'<td>{escape(row.get("journal", ""))}</td>'
                f'<td>{escape(row.get("journal_tier", ""))}</td>'
                f'<td>{escape(row.get("subdomain", ""))}</td>'
                f'<td class="number">{escape(row.get("citation_count", 0))}</td>'
                f'<td class="number">{escape(row.get("research_value_score", 0))}</td>'
                "</tr>"
            )
        return (
            '<div class="table-wrap"><table>'
            "<thead><tr><th>#</th><th>类型</th><th>Title</th><th>Journal</th><th>期刊层级</th><th>Topic</th><th>引用</th><th>价值分</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>"
        )

    def year_chart(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        body = []
        max_count = max(int(row.get("paper_count") or 0) for row in rows) or 1
        for row in rows:
            count = int(row.get("paper_count") or 0)
            citations = int(row.get("citation_count") or 0)
            width = max(4, round(count / max_count * 100, 2))
            body.append(
                "<tr>"
                f'<td>{escape(row.get("year", ""))}</td>'
                f'<td class="number">{count}</td>'
                f'<td class="number">{citations}</td>'
                '<td><div class="mini-track">'
                f'<div class="mini-fill" style="width:{width}%"></div>'
                "</div></td>"
                "</tr>"
            )
        return (
            '<div class="table-wrap year-table"><table>'
            '<thead><tr><th>年份</th><th class="number">论文</th><th class="number">引用</th><th>规模</th></tr></thead>'
            f"<tbody>{''.join(body)}</tbody></table></div>"
        )

    def paper_table(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        body = []
        for row in rows:
            body.append(
                "<tr>"
                f'<td class="paper-title">{escape(row.get("title", ""))}</td>'
                f'<td>{escape(row.get("journal", ""))}</td>'
                f'<td>{escape(row.get("year", ""))}</td>'
                f'<td>{escape(row.get("subdomain", ""))}</td>'
                f'<td class="number">{escape(row.get("citation_count", 0))}</td>'
                "</tr>"
            )
        return (
            '<div class="table-wrap"><table>'
            "<thead><tr><th>Title</th><th>Journal</th><th>Year</th><th>Subdomain</th><th>Citations</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>"
        )

    def reference_table(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        body = []
        for row in rows:
            body.append(
                "<tr>"
                f'<td class="paper-title">{escape(row.get("title", ""))}</td>'
                f'<td>{escape(row.get("journal", ""))}</td>'
                f'<td>{escape(row.get("year", ""))}</td>'
                f'<td class="number">{escape(row.get("source_article_count", 0))}</td>'
                f'<td class="number">{escape(row.get("relevance_score", 0))}</td>'
                f'<td class="number">{escape(row.get("value_score", 0))}</td>'
                f'<td>{escape(row.get("journal_tier", ""))}</td>'
                "</tr>"
            )
        return (
            '<div class="table-wrap"><table>'
            "<thead><tr><th>Title</th><th>Journal</th><th>Year</th><th>被样本文献引用</th><th>相关性</th><th>价值分</th><th>期刊层级</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>"
        )

    def styles(self) -> str:
        return """
:root { color-scheme: light; --ink:#1f2933; --muted:#5f6c7b; --line:#d9e2ec; --paper:#ffffff; --bg:#f5f7fa; --green:#2f7d64; --blue:#2d6cdf; --gold:#b7791f; }
* { box-sizing: border-box; }
body { margin:0; font-family: Arial, "Microsoft YaHei", sans-serif; color:var(--ink); background:var(--bg); letter-spacing:0; }
main { max-width:1180px; margin:0 auto; padding:28px 20px 42px; }
.page-header { display:flex; justify-content:space-between; gap:16px; align-items:end; margin-bottom:18px; }
.eyebrow { margin:0 0 4px; color:var(--green); font-size:13px; font-weight:700; text-transform:uppercase; }
h1 { margin:0; font-size:34px; line-height:1.1; }
.range { margin:0; color:var(--muted); font-size:14px; }
.metrics { display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); gap:10px; margin-bottom:14px; }
.metric { background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; }
.metric span { display:block; color:var(--muted); font-size:13px; margin-bottom:6px; }
.metric strong { display:block; font-size:24px; line-height:1.1; overflow-wrap:anywhere; }
.grid { display:grid; gap:14px; margin-top:14px; }
.grid.two { grid-template-columns:repeat(2, minmax(0, 1fr)); }
.panel { background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }
.panel.wide { margin-top:14px; }
h2 { margin:0 0 14px; font-size:18px; line-height:1.25; }
.brief-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }
.brief-card { border:1px solid var(--line); border-radius:8px; padding:12px; min-width:0; background:#fbfdff; }
.brief-card h3 { margin:0 0 8px; font-size:14px; color:var(--green); }
.brief-card p { margin:0 0 7px; color:var(--ink); font-size:13px; line-height:1.35; overflow-wrap:anywhere; }
.brief-card p:last-child { margin-bottom:0; }
.brief-note { margin:12px 0 0; color:var(--muted); font-size:13px; }
.chart-note { margin:10px 0 0; color:var(--muted); font-size:12px; }
.bar-chart { display:grid; gap:10px; }
.bar-row { display:grid; grid-template-columns:minmax(120px, 1.2fr) minmax(120px, 2fr) 94px; gap:10px; align-items:center; min-height:24px; }
.bar-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink); font-size:13px; }
.bar-track { height:12px; border-radius:8px; background:#edf2f7; overflow:hidden; }
.bar-fill { height:100%; border-radius:8px; background:linear-gradient(90deg, var(--green), var(--blue)); }
.bar-value { color:var(--muted); font-size:12px; text-align:right; white-space:nowrap; display:flex; justify-content:flex-end; gap:6px; }
.mini-track { height:10px; min-width:110px; border-radius:8px; background:#edf2f7; overflow:hidden; }
.mini-fill { height:100%; border-radius:8px; background:var(--gold); }
.year-table table { min-width:420px; }
.table-wrap { overflow:auto; }
table { width:100%; border-collapse:collapse; min-width:760px; }
th, td { padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; font-size:13px; vertical-align:top; }
th { color:var(--muted); font-weight:700; }
.paper-title { max-width:460px; }
.number { text-align:right; font-variant-numeric:tabular-nums; }
.empty { color:var(--muted); margin:0; }
@media (max-width: 860px) {
  main { padding:20px 12px 32px; }
  .page-header { display:block; }
  h1 { font-size:28px; }
  .metrics { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .brief-grid { grid-template-columns:1fr; }
  .grid.two { grid-template-columns:1fr; }
  .bar-row { grid-template-columns:1fr 1.4fr 88px; }
}
"""


def escape(value) -> str:
    return html.escape(str(value if value is not None else ""))


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp visualize."""
    writer = ResearchDashboardWriter(
        Path(args.manifest),
        out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        top_n=getattr(args, "top", 15),
    )
    writer.write()
    return 0

