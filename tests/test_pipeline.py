# -*- coding: utf-8 -*-

import json

import pytest

from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pipeline import SurveyPipelineService, run_from_args


def test_survey_pipeline_wires_default_directories_and_steps(monkeypatch, tmp_path):
    calls = []

    def fake_download(self):
        calls.append((
            "download",
            self.output_dir,
            self.results_dir,
            self.journals,
            self.limit,
            self.article_filter,
            self.download_workers,
            self.download_pdfs,
        ))
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

    def fake_reference_analysis(self):
        calls.append(("references", self.manifest_path, self.out_dir, self.max_reference_downloads))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "reference_manifest.json").write_text("[]", encoding="utf-8")
        return []

    monkeypatch.setattr("litsurveygrp.pipeline.MultiJournalDownloadService.run", fake_download)
    monkeypatch.setattr("litsurveygrp.pipeline.MetadataEnrichmentService.run", fake_enrich)
    monkeypatch.setattr("litsurveygrp.pipeline.PaperClassificationService.run", fake_classify)
    monkeypatch.setattr("litsurveygrp.pipeline.ResearchStatsWriter.write", fake_stats)
    monkeypatch.setattr("litsurveygrp.pipeline.ResearchDashboardWriter.write", fake_dashboard)
    monkeypatch.setattr("litsurveygrp.pipeline.ReferenceAnalysisService.run", fake_reference_analysis)

    service = SurveyPipelineService(
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        query="LLM causal discovery",
        from_year=2024,
        to_year=2026,
        limit=50,
        download_workers=3,
        download_pdfs=False,
        keywords=["senescence", "immune"],
        article_types=["Article"],
        min_citations=2,
        authors=["Alice"],
        institutions=["Institute"],
        filter_sources=["openalex"],
        analyze_references=True,
        max_references_per_paper=30,
        max_reference_downloads=5,
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
    assert outputs.references_dir.name == "references"
    assert outputs.final_manifest == outputs.classified_manifest
    assert [call[0] for call in calls] == ["download", "enrich", "classify", "stats", "visualize", "references"]
    assert calls[0][1].name == "papers"
    assert calls[0][2].name == "results"
    assert calls[0][3][0].provider == "openalex-search"
    assert calls[0][3][0].query == "LLM causal discovery"
    assert calls[0][4] == 50
    assert calls[0][6] == 3
    assert calls[0][7] is False
    assert calls[0][5].keywords == ["senescence", "immune"]
    assert calls[0][5].article_types == ["Article"]
    assert calls[0][5].min_citations == 2
    assert calls[0][5].from_year == 2024
    assert calls[0][5].to_year == 2026
    assert calls[0][5].authors == ["Alice"]
    assert calls[0][5].institutions == ["Institute"]
    assert calls[1][3] == ["openalex", "semantic-scholar", "europe-pmc", "crossref"]
    assert calls[2][4] == "allenai-specter"
    assert calls[3][2].name == "stats"
    assert calls[5][3] == 5
    assert report["final_manifest"].endswith("classified_manifest.json")
    assert report["steps"]["enrichment"] is True
    assert report["steps"]["reference_analysis"] is True
    assert report["reference_analysis"]["max_references_per_paper"] == 30


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

    monkeypatch.setattr("litsurveygrp.pipeline.MultiJournalDownloadService.run", fake_download)

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
        "reference_analysis": False,
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
        query = "LLM causal discovery"
        year = 2026
        from_year = 2024
        to_year = 2026
        limit = 5
        per_journal_limit = 20
        download_timeout = 7
        download_workers = 4
        download_pdfs = False
        pdf_only_candidates = True
        dry_run = True
        keyword = ["aging", "senescence"]
        article_type = ["Article"]
        min_citations = 10
        author = ["Alice"]
        institution = ["Institute"]
        filter_sources = ["openalex", "crossref"]
        skip_enrichment = False
        sources = ["openalex", "crossref"]
        metadata_timeout = 8
        request_interval = 1.5
        skip_classification = False
        move = False
        sentence_model = "allenai-specter"
        skip_stats = False
        skip_visualization = False
        analyze_references = True
        out_dir = str(tmp_path / "references")
        max_references_per_paper = 25
        max_total_references = 250
        reference_relevance_threshold = 0.35
        max_reference_downloads = 6
        min_reference_value_score = 0.55
        require_reference_doi = True
        reference_query = "immune aging"
        reference_sources = ["openalex"]
        top = 9
        clean_existing = True

    captured = {}

    def fake_run(self):
        captured["papers_dir"] = self.papers_dir
        captured["results_dir"] = self.results_dir
        captured["journal_specs"] = self.journal_specs
        captured["query"] = self.query
        captured["limit"] = self.limit
        captured["download_workers"] = self.download_workers
        captured["download_pdfs"] = self.download_pdfs
        captured["article_filter"] = self.article_filter
        captured["filter_sources"] = self.filter_sources
        captured["request_interval"] = self.request_interval
        captured["metadata_sources"] = self.metadata_sources
        captured["analyze_references"] = self.analyze_references
        captured["reference_out_dir"] = self.reference_out_dir
        captured["max_reference_downloads"] = self.max_reference_downloads
        captured["reference_sources"] = self.reference_sources
        captured["clean_existing"] = self.clean_existing
        return None

    monkeypatch.setattr(SurveyPipelineService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["papers_dir"].name == "papers"
    assert captured["results_dir"].name == "results"
    assert captured["journal_specs"] == ["nature-aging"]
    assert captured["query"] == "LLM causal discovery"
    assert captured["limit"] == 5
    assert captured["download_workers"] == 4
    assert captured["download_pdfs"] is False
    assert captured["article_filter"].keywords == ["aging", "senescence"]
    assert captured["article_filter"].article_types == ["Article"]
    assert captured["article_filter"].min_citations == 10
    assert captured["article_filter"].authors == ["Alice"]
    assert captured["article_filter"].institutions == ["Institute"]
    assert captured["filter_sources"] == ["openalex", "crossref"]
    assert captured["request_interval"] == 1.5
    assert captured["metadata_sources"] == ["openalex", "crossref"]
    assert captured["analyze_references"] is True
    assert captured["reference_out_dir"].name == "references"
    assert captured["max_reference_downloads"] == 6
    assert captured["reference_sources"] == ["openalex"]
    assert captured["clean_existing"] is True

