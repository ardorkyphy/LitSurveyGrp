# -*- coding: utf-8 -*-

import json

import pytest

from refchaser.paper_models import ArticleRecord
from refchaser.pipeline import SurveyPipelineService, run_from_args


def test_survey_pipeline_wires_default_directories_and_steps(monkeypatch, tmp_path):
    calls = []

    def fake_download(self):
        calls.append(("download", self.output_dir, self.results_dir, self.journals, self.limit))
        self.results_dir.mkdir(parents=True, exist_ok=True)
        article = ArticleRecord(title="Aging paper", doi="10.1/test")
        (self.results_dir / "article_manifest.json").write_text(
            json.dumps([article.to_manifest_dict()], ensure_ascii=False),
            encoding="utf-8",
        )
        (self.results_dir / "download_report.csv").write_text("title\nAging paper\n", encoding="utf-8")
        return [article]

    def fake_enrich(self):
        calls.append(("enrich", self.manifest_path, self.output_path, self.sources, self.request_interval))
        article = ArticleRecord(title="Aging paper", doi="10.1/test", citation_count=7)
        self.write_manifest([article])
        return [article]

    def fake_classify(self):
        calls.append(("classify", self.manifest_path, self.root_dir, self.organize_dir, self.sentence_model))
        article = ArticleRecord(title="Aging paper", doi="10.1/test", subdomain="Topic_Aging")
        self.write_classified_manifest([article])
        return [article]

    def fake_stats(self):
        calls.append(("stats", self.manifest_path, self.out_dir, self.top_n))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "summary.json"
        path.write_text("{}", encoding="utf-8")
        return {"summary": path}

    def fake_dashboard(self):
        calls.append(("visualize", self.manifest_path, self.out_dir, self.top_n))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "research_dashboard.html"
        path.write_text("<html></html>", encoding="utf-8")
        return path

    monkeypatch.setattr("refchaser.pipeline.MultiJournalDownloadService.run", fake_download)
    monkeypatch.setattr("refchaser.pipeline.MetadataEnrichmentService.run", fake_enrich)
    monkeypatch.setattr("refchaser.pipeline.PaperClassificationService.run", fake_classify)
    monkeypatch.setattr("refchaser.pipeline.ResearchStatsWriter.write", fake_stats)
    monkeypatch.setattr("refchaser.pipeline.ResearchDashboardWriter.write", fake_dashboard)

    service = SurveyPipelineService(
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        journal_specs=["nature-aging"],
        year=2026,
        limit=50,
        request_interval=1.0,
        top_n=12,
    )

    outputs = service.run()
    report = json.loads(outputs.pipeline_report.read_text(encoding="utf-8"))

    assert outputs.download_manifest.name == "article_manifest.json"
    assert outputs.enriched_manifest.name == "enriched_manifest.json"
    assert outputs.classified_manifest.name == "classified_manifest.json"
    assert outputs.stats_dir.name == "stats"
    assert outputs.dashboard.name == "research_dashboard.html"
    assert outputs.final_manifest == outputs.classified_manifest
    assert [call[0] for call in calls] == ["download", "enrich", "classify", "stats", "visualize"]
    assert calls[0][1].name == "papers"
    assert calls[0][2].name == "results"
    assert calls[0][4] == 50
    assert calls[1][3] == ["openalex", "semantic-scholar", "europe-pmc", "crossref"]
    assert calls[2][4] == "allenai-specter"
    assert calls[3][2].name == "stats"
    assert report["final_manifest"].endswith("classified_manifest.json")
    assert report["steps"]["enrichment"] is True


def test_survey_pipeline_can_skip_optional_steps(monkeypatch, tmp_path):
    def fake_download(self):
        self.results_dir.mkdir(parents=True, exist_ok=True)
        article = ArticleRecord(title="Aging paper")
        (self.results_dir / "article_manifest.json").write_text(
            json.dumps([article.to_manifest_dict()], ensure_ascii=False),
            encoding="utf-8",
        )
        (self.results_dir / "download_report.csv").write_text("title\n", encoding="utf-8")
        return [article]

    monkeypatch.setattr("refchaser.pipeline.MultiJournalDownloadService.run", fake_download)

    service = SurveyPipelineService(
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        enrich_metadata=False,
        classify_papers=False,
        write_stats=False,
        write_visualization=False,
    )

    outputs = service.run()
    report = json.loads(outputs.pipeline_report.read_text(encoding="utf-8"))

    assert outputs.final_manifest == tmp_path / "results" / "article_manifest.json"
    assert outputs.enriched_manifest is None
    assert outputs.classified_manifest is None
    assert report["steps"] == {
        "download": True,
        "enrichment": False,
        "classification": False,
        "stats": False,
        "visualization": False,
    }


def test_survey_pipeline_refuses_to_clean_workspace_root(tmp_path):
    service = SurveyPipelineService(
        papers_dir=tmp_path,
        results_dir=tmp_path / "results",
        clean_existing=True,
    )

    with pytest.raises(ValueError):
        service._clean_generated_dir(tmp_path.cwd())


def test_pipeline_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        papers_dir = str(tmp_path / "papers")
        results_dir = str(tmp_path / "results")
        journal = ["nature-aging"]
        year = 2026
        limit = 5
        per_journal_limit = 20
        download_timeout = 7
        pdf_only_candidates = True
        dry_run = True
        skip_enrichment = False
        sources = ["openalex", "crossref"]
        metadata_timeout = 8
        request_interval = 1.5
        skip_classification = False
        move = False
        sentence_model = "allenai-specter"
        skip_stats = False
        skip_visualization = False
        top = 9
        clean_existing = True

    captured = {}

    def fake_run(self):
        captured["papers_dir"] = self.papers_dir
        captured["results_dir"] = self.results_dir
        captured["journal_specs"] = self.journal_specs
        captured["limit"] = self.limit
        captured["request_interval"] = self.request_interval
        captured["metadata_sources"] = self.metadata_sources
        captured["clean_existing"] = self.clean_existing
        return None

    monkeypatch.setattr(SurveyPipelineService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["papers_dir"].name == "papers"
    assert captured["results_dir"].name == "results"
    assert captured["journal_specs"] == ["nature-aging"]
    assert captured["limit"] == 5
    assert captured["request_interval"] == 1.5
    assert captured["metadata_sources"] == ["openalex", "crossref"]
    assert captured["clean_existing"] is True
