# -*- coding: utf-8 -*-

import json

from litsurveygrp.paper_models import ArticleRecord, ReferenceRecord
from litsurveygrp.visualization import ResearchDashboardWriter, run_from_args


def test_research_dashboard_writer_generates_offline_html(tmp_path):
    manifest = tmp_path / "中文路径" / "enriched_manifest.json"
    manifest.parent.mkdir()
    articles = [
        ArticleRecord(
            title="Biomarker paper",
            journal="Nature Aging",
            publish_date="2026-01-02",
            authors=["Alice"],
            institutions=["Institute A"],
            subdomain="Topic_Biomarker",
            article_type="research-article",
            citation_count=20,
            citation_source="openalex",
            references=[
                ReferenceRecord(
                    title="Core cited reference",
                    journal="Nature",
                    publish_date="2020",
                    source_article_count=2,
                    relevance_score=0.7,
                    value_score=0.8,
                    journal_tier="top_general",
                )
            ],
        ),
        ArticleRecord(
            title="Mechanism paper",
            journal="Science",
            publish_date="2025-01-02",
            authors=["Bob"],
            institutions=["Institute B"],
            subdomain="Topic_Mechanism",
            article_type="review-article",
            citation_count=5,
            citation_source="crossref",
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles], ensure_ascii=False), encoding="utf-8")
    writer = ResearchDashboardWriter(manifest, top_n=10)

    path = writer.write()
    html = path.read_text(encoding="utf-8")

    assert path.name == "research_dashboard.html"
    assert path.parent.name == "visualization"
    assert "Research Dashboard" in html
    assert "研究画像摘要" in html
    assert "研究子领域分布" in html
    assert "子领域档案" in html
    assert "推荐阅读路径" in html
    assert "年份趋势" in html
    assert "关键论文" in html
    assert "核心引用文献" in html
    assert "20引" in html
    assert "Biomarker paper" in html
    assert "Core cited reference" in html
    assert "Topic_Biomarker" in html
    assert '<div class="table-wrap year-table">' in html
    assert '<th>年份</th><th class="number">论文</th><th class="number">引用</th><th>规模</th>' in html
    assert 'aria-label="Year trend"' not in html
    assert "https://cdn" not in html
    assert "<script id=\"dashboard-data\"" in html


def test_research_dashboard_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        out_dir = str(tmp_path / "图表")
        top = 6

    captured = {}

    def fake_write(self):
        captured["out_dir"] = self.out_dir
        captured["top_n"] = self.top_n
        return self.out_dir / "research_dashboard.html"

    monkeypatch.setattr(ResearchDashboardWriter, "write", fake_write)

    assert run_from_args(Args()) == 0
    assert captured["out_dir"].name == "图表"
    assert captured["top_n"] == 6

