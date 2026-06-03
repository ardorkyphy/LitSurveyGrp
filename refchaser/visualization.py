# -*- coding: utf-8 -*-
"""Self-contained HTML visualizations for research survey manifests."""

import html
import json
from pathlib import Path

from refchaser.research_stats import ResearchStatsWriter


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
        subdomains = self.stats.subdomain_stats(articles)[: self.top_n]
        years = self.stats.year_trend(articles)
        authors = self.stats.author_stats(articles)[: self.top_n]
        institutions = self.stats.institution_stats(articles)[: self.top_n]
        journals = self.stats.journal_stats(articles)[: self.top_n]
        article_types = self.stats.article_type_stats(articles)
        top_papers = self.stats.top_papers(articles)[: self.top_n]
        data_json = html.escape(json.dumps({
            "summary": summary,
            "subdomains": subdomains,
            "years": years,
            "authors": authors,
            "institutions": institutions,
            "journals": journals,
            "article_types": article_types,
            "top_papers": top_papers,
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
            '<section class="grid two">',
            self.panel("研究子领域分布", self.bar_chart(subdomains, "subdomain", "paper_count", "citation_count")),
            self.panel("年份趋势", self.year_chart(years)),
            "</section>",
            '<section class="grid two">',
            self.panel("高产作者", self.bar_chart(authors, "author", "paper_count", "citation_count")),
            self.panel("高产机构", self.bar_chart(institutions, "institution", "paper_count", "citation_count")),
            "</section>",
            '<section class="grid two">',
            self.panel("期刊分布", self.bar_chart(journals, "journal", "paper_count", "citation_count")),
            self.panel("文章类型", self.bar_chart(article_types, "article_type", "paper_count", "citation_count")),
            "</section>",
            self.panel("关键论文", self.paper_table(top_papers), wide=True),
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
                f'<div class="bar-value">{count} / {citations}</div>'
                "</div>"
            )
        return '<div class="bar-chart">' + "".join(items) + "</div>"

    def year_chart(self, rows: list[dict]) -> str:
        if not rows:
            return '<p class="empty">No data</p>'
        clean_rows = [row for row in rows if row.get("year") != "Unknown"]
        if not clean_rows:
            return self.bar_chart(rows, "year", "paper_count", "citation_count")
        max_count = max(int(row.get("paper_count") or 0) for row in clean_rows) or 1
        if len(clean_rows) == 1:
            points = [(160, 32)]
        else:
            points = []
            for index, row in enumerate(clean_rows):
                x = 32 + index * (296 / (len(clean_rows) - 1))
                y = 168 - (int(row.get("paper_count") or 0) / max_count * 136)
                points.append((round(x, 2), round(y, 2)))
        point_attr = " ".join(f"{x},{y}" for x, y in points)
        circles = "".join(f'<circle cx="{x}" cy="{y}" r="4"></circle>' for x, y in points)
        labels = "".join(
            f'<span style="left:{round((x - 32) / 296 * 100, 2)}%">{escape(row.get("year"))}</span>'
            for (x, _), row in zip(points, clean_rows)
        )
        return (
            '<div class="line-wrap">'
            '<svg viewBox="0 0 360 190" role="img" aria-label="Year trend">'
            '<line x1="28" y1="170" x2="340" y2="170"></line>'
            '<line x1="28" y1="24" x2="28" y2="170"></line>'
            f'<polyline points="{point_attr}"></polyline>{circles}'
            "</svg>"
            f'<div class="year-labels">{labels}</div>'
            "</div>"
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
.metrics { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; margin-bottom:14px; }
.metric { background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; }
.metric span { display:block; color:var(--muted); font-size:13px; margin-bottom:6px; }
.metric strong { display:block; font-size:24px; line-height:1.1; overflow-wrap:anywhere; }
.grid { display:grid; gap:14px; margin-top:14px; }
.grid.two { grid-template-columns:repeat(2, minmax(0, 1fr)); }
.panel { background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }
.panel.wide { margin-top:14px; }
h2 { margin:0 0 14px; font-size:18px; line-height:1.25; }
.bar-chart { display:grid; gap:10px; }
.bar-row { display:grid; grid-template-columns:minmax(120px, 1.2fr) minmax(120px, 2fr) 72px; gap:10px; align-items:center; min-height:24px; }
.bar-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink); font-size:13px; }
.bar-track { height:12px; border-radius:8px; background:#edf2f7; overflow:hidden; }
.bar-fill { height:100%; border-radius:8px; background:linear-gradient(90deg, var(--green), var(--blue)); }
.bar-value { color:var(--muted); font-size:12px; text-align:right; white-space:nowrap; }
.line-wrap { position:relative; padding-bottom:22px; }
svg { width:100%; height:240px; display:block; }
svg line { stroke:var(--line); stroke-width:2; }
svg polyline { fill:none; stroke:var(--gold); stroke-width:4; stroke-linejoin:round; stroke-linecap:round; }
svg circle { fill:var(--blue); }
.year-labels { position:absolute; left:32px; right:32px; bottom:0; height:18px; }
.year-labels span { position:absolute; transform:translateX(-50%); color:var(--muted); font-size:12px; white-space:nowrap; }
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
  .grid.two { grid-template-columns:1fr; }
  .bar-row { grid-template-columns:1fr 1.4fr 62px; }
}
"""


def escape(value) -> str:
    return html.escape(str(value if value is not None else ""))


def run_from_args(args) -> int:
    """CLI adapter for python -m refchaser visualize."""
    writer = ResearchDashboardWriter(
        Path(args.manifest),
        out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        top_n=getattr(args, "top", 15),
    )
    writer.write()
    return 0
