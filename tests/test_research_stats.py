# -*- coding: utf-8 -*-

import csv
import json

from refchaser.paper_models import ArticleRecord
from refchaser.research_stats import (
    ResearchStatsWriter,
    citation_bucket,
    collaboration_type,
    extract_year,
    run_from_args,
    team_label,
)


def test_extract_year_accepts_common_date_formats():
    assert extract_year("2026-01-02") == "2026"
    assert extract_year("2026/01/02") == "2026"
    assert extract_year("") == ""


def test_team_label_prefers_lead_institution_then_authors():
    assert team_label(ArticleRecord(title="A", institutions=["Institute A"], authors=["Alice", "Bob"])) == "Institute A"
    assert team_label(ArticleRecord(title="B", authors=["Alice", "Bob"])) == "Alice + Bob"
    assert team_label(ArticleRecord(title="C")) == "Unknown"


def test_citation_bucket_and_collaboration_type_are_research_oriented():
    assert citation_bucket(0) == "0"
    assert citation_bucket(9) == "1-9"
    assert citation_bucket(50) == "50-99"
    assert citation_bucket(100) == "100+"
    assert collaboration_type(ArticleRecord(title="A", authors=["A"], institutions=["I"])) == "single_author_single_institution"
    assert collaboration_type(
        ArticleRecord(title="B", authors=["A", "B", "C", "D"], institutions=["I1", "I2"])
    ) == "medium_team_multi_institution"


def test_research_stats_writer_builds_research_outputs(tmp_path):
    manifest = tmp_path / "中文路径" / "enriched_manifest.json"
    manifest.parent.mkdir()
    articles = [
        ArticleRecord(
            title="Highly cited biomarker paper",
            doi="10.1/high",
            journal="Nature Aging",
            publish_date="2026-01-02",
            authors=["Alice", "Bob"],
            institutions=["Institute A", "Institute C"],
            article_type="research-article",
            subdomain="Topic_Biomarker",
            citation_count=30,
            citation_source="openalex",
        ),
        ArticleRecord(
            title="Review on healthspan",
            doi="10.1/review",
            journal="Science",
            publish_date="2025/03/04",
            authors=["Alice", "Chen"],
            institutions=["Institute B"],
            article_type="review-article",
            subdomain="Review",
            citation_count=12,
            citation_source="crossref",
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles], ensure_ascii=False), encoding="utf-8")
    writer = ResearchStatsWriter(manifest, top_n=10)

    outputs = writer.write()
    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))

    assert outputs["subdomains"].name == "subdomain_stats.csv"
    assert outputs["top_papers"].name == "top_papers.csv"
    assert outputs["journals"].name == "journal_stats.csv"
    assert outputs["subdomain_years"].name == "subdomain_year_trend.csv"
    assert outputs["citation_buckets"].name == "citation_bucket_stats.csv"
    assert outputs["collaboration"].name == "collaboration_stats.csv"
    assert summary["total_papers"] == 2
    assert summary["year_min"] == "2025"
    assert summary["year_max"] == "2026"
    assert summary["unique_authors"] == 3
    assert summary["unique_institutions"] == 3
    assert summary["total_citations"] == 42
    assert "download_status" not in summary

    top_rows = read_csv(outputs["top_papers"])
    author_rows = read_csv(outputs["authors"])
    team_rows = read_csv(outputs["teams"])
    journal_rows = read_csv(outputs["journals"])
    subdomain_year_rows = read_csv(outputs["subdomain_years"])
    bucket_rows = read_csv(outputs["citation_buckets"])
    collaboration_rows = read_csv(outputs["collaboration"])

    assert top_rows[0]["title"] == "Highly cited biomarker paper"
    assert top_rows[0]["citation_source"] == "openalex"
    assert author_rows[0]["author"] == "Alice"
    assert author_rows[0]["paper_count"] == "2"
    assert team_rows[0]["team"] == "Institute A"
    assert journal_rows[0]["journal"] == "Nature Aging"
    assert subdomain_year_rows[0]["year"] == "2025"
    assert subdomain_year_rows[1]["subdomain"] == "Topic_Biomarker"
    assert bucket_rows[0]["citation_bucket"] == "10-49"
    assert collaboration_rows[0]["collaboration_type"] == "small_team_multi_institution"


def test_research_stats_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        out_dir = str(tmp_path / "自定义stats")
        top = 5

    captured = {}

    def fake_write(self):
        captured["out_dir"] = self.out_dir
        captured["top_n"] = self.top_n
        return {}

    monkeypatch.setattr(ResearchStatsWriter, "write", fake_write)

    assert run_from_args(Args()) == 0
    assert captured["out_dir"].name == "自定义stats"
    assert captured["top_n"] == 5


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
