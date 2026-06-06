# -*- coding: utf-8 -*-

import json

import pytest

from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pipeline import SurveyCommandConfig, SurveyCommandService, SurveyPipelineService, run_from_args, run_survey_from_args


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
        metadata_cache_dir=tmp_path / "cache",
        use_metadata_cache=True,
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
    assert report["metadata_cache"]["enabled"] is True
    assert report["metadata_cache"]["dir"].endswith("cache")
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


def test_survey_pipeline_uses_metadata_cache_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LITSURVEYGRP_METADATA_CACHE_DIR", str(tmp_path / "env_cache"))
    service = SurveyPipelineService(
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
    )

    assert service.effective_metadata_cache_dir().name == "env_cache"


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
        metadata_cache_dir = str(tmp_path / "cache")
        no_metadata_cache = True

    captured = {}

    def fake_run(self):
        captured["papers_dir"] = self.papers_dir
        captured["results_dir"] = self.results_dir
        captured["journal_specs"] = self.journal_specs
        captured["query"] = self.query
        captured["limit"] = self.limit
        captured["download_workers"] = self.download_workers
        captured["download_pdfs"] = self.download_pdfs
        captured["metadata_cache_dir"] = self.metadata_cache_dir
        captured["use_metadata_cache"] = self.use_metadata_cache
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
    assert captured["metadata_cache_dir"].name == "cache"
    assert captured["use_metadata_cache"] is False
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


def test_survey_command_service_runs_core_stages_in_order(monkeypatch, tmp_path):
    calls = []

    class FakePipelineOutputs:
        def __init__(self, results_dir):
            self.download_manifest = results_dir / "article_manifest.json"
            self.final_manifest = results_dir / "classified_manifest.json"

    def fake_pipeline_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_pipeline_run(self):
        calls.append(("pipeline", self.kwargs))
        results_dir = self.kwargs["results_dir"]
        results_dir.mkdir(parents=True, exist_ok=True)
        return FakePipelineOutputs(results_dir)

    def fake_pdf_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_pdf_run(self):
        calls.append(("pdf", self.kwargs))
        manifest = self.kwargs["results_dir"] / "pdf_downloaded_manifest.json"
        manifest.write_text("[]", encoding="utf-8")
        return {"manifest": manifest}

    def fake_agent_input_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_agent_input_run(self):
        calls.append(("agent_input", self.kwargs))
        self.kwargs["out_dir"].mkdir(parents=True, exist_ok=True)
        return {}

    def fake_paper_reader_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_paper_reader_run(self):
        calls.append(("paper_reader", self.kwargs))
        return {}

    def fake_domain_synth_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_domain_synth_run(self):
        calls.append(("domain_synth", self.kwargs))
        return {}

    def fake_report_init(self, **kwargs):
        self.kwargs = kwargs

    def fake_report_build(self):
        calls.append(("report", self.kwargs))
        results_dir = self.kwargs["results_dir"]
        md = results_dir / "final_survey_report.md"
        html = results_dir / "final_survey_report.html"
        md.write_text("# report", encoding="utf-8")
        html.write_text("<html></html>", encoding="utf-8")
        return {"markdown": md, "html": html}

    monkeypatch.setattr("litsurveygrp.pipeline.SurveyPipelineService.__init__", fake_pipeline_init)
    monkeypatch.setattr("litsurveygrp.pipeline.SurveyPipelineService.run", fake_pipeline_run)
    monkeypatch.setattr("litsurveygrp.pipeline.TopPdfDownloadService.__init__", fake_pdf_init)
    monkeypatch.setattr("litsurveygrp.pipeline.TopPdfDownloadService.run", fake_pdf_run)
    monkeypatch.setattr("litsurveygrp.pipeline.AgentInputPreparer.__init__", fake_agent_input_init)
    monkeypatch.setattr("litsurveygrp.pipeline.AgentInputPreparer.run", fake_agent_input_run)
    monkeypatch.setattr("litsurveygrp.pipeline.PaperReaderAgent.__init__", fake_paper_reader_init)
    monkeypatch.setattr("litsurveygrp.pipeline.PaperReaderAgent.run", fake_paper_reader_run)
    monkeypatch.setattr("litsurveygrp.pipeline.DomainSynthesizerAgent.__init__", fake_domain_synth_init)
    monkeypatch.setattr("litsurveygrp.pipeline.DomainSynthesizerAgent.run", fake_domain_synth_run)
    monkeypatch.setattr("litsurveygrp.pipeline.FinalSurveyReportBuilder.__init__", fake_report_init)
    monkeypatch.setattr("litsurveygrp.pipeline.FinalSurveyReportBuilder.build", fake_report_build)
    monkeypatch.setattr(
        "litsurveygrp.pipeline.ReferenceAnalysisService.run",
        lambda self: calls.append(("references", self.out_dir)) or [],
    )

    outputs = SurveyCommandService(SurveyCommandConfig(
        out_dir=tmp_path / "run",
        query="AI in neuroscience",
        limit=200,
        top_papers=30,
        top_domains=8,
        per_domain=20,
        domain_rules="rules.json",
        enrichment_workers=4,
        classification_workers=3,
        agent_provider="dry-run",
    )).run()

    assert [call[0] for call in calls] == [
        "pipeline",
        "pdf",
        "agent_input",
        "paper_reader",
        "domain_synth",
        "report",
    ]
    assert calls[0][1]["results_dir"] == tmp_path / "run" / "results"
    assert calls[0][1]["papers_dir"] == tmp_path / "run" / "papers"
    assert calls[0][1]["download_pdfs"] is False
    assert calls[0][1]["domain_rules"] == "rules.json"
    assert calls[0][1]["enrichment_workers"] == 4
    assert calls[0][1]["classification_workers"] == 3
    assert calls[1][1]["top"] == 30
    assert calls[2][1]["top_domains"] == 8
    assert calls[2][1]["per_domain"] == 20
    assert calls[3][1]["provider"] == "dry-run"
    assert calls[5][1]["agent_dir"] == tmp_path / "run" / "agent_inputs"
    assert outputs.final_manifest.name == "pdf_downloaded_manifest.json"
    assert outputs.html_report.name == "final_survey_report.html"
    assert outputs.references_dir is None


def test_survey_command_service_can_analyze_references_between_pdf_and_agents(monkeypatch, tmp_path):
    calls = []

    class FakePipelineOutputs:
        download_manifest = tmp_path / "run" / "results" / "article_manifest.json"
        final_manifest = tmp_path / "run" / "results" / "classified_manifest.json"

    def fake_reference_init(self, manifest_path, **kwargs):
        self.manifest_path = manifest_path
        self.out_dir = kwargs["out_dir"]
        self.max_references_per_paper = kwargs["max_references_per_paper"]
        self.max_total_references = kwargs["max_total_references"]
        self.relevance_threshold = kwargs["relevance_threshold"]
        self.max_reference_downloads = kwargs["max_reference_downloads"]
        self.min_value_score = kwargs["min_value_score"]
        self.require_doi_for_download = kwargs["require_doi_for_download"]
        self.reference_query = kwargs["reference_query"]
        self.metadata_sources = kwargs["metadata_sources"]

    monkeypatch.setattr("litsurveygrp.pipeline.SurveyPipelineService.run", lambda self: calls.append("pipeline") or FakePipelineOutputs())
    monkeypatch.setattr("litsurveygrp.pipeline.TopPdfDownloadService.run", lambda self: calls.append("pdf") or {"manifest": tmp_path / "pdf.json"})
    monkeypatch.setattr("litsurveygrp.pipeline.ReferenceAnalysisService.__init__", fake_reference_init)
    monkeypatch.setattr("litsurveygrp.pipeline.ReferenceAnalysisService.run", lambda self: calls.append(("references", self)) or [])
    monkeypatch.setattr("litsurveygrp.pipeline.AgentInputPreparer.run", lambda self: calls.append("agent_input") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.PaperReaderAgent.run", lambda self: calls.append("paper_reader") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.DomainSynthesizerAgent.run", lambda self: calls.append("domain_synth") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.FinalSurveyReportBuilder.build", lambda self: calls.append("report") or {
        "markdown": tmp_path / "report.md",
        "html": tmp_path / "report.html",
    })

    outputs = SurveyCommandService(SurveyCommandConfig(
        out_dir=tmp_path / "run",
        analyze_references=True,
        max_references_per_paper=40,
        max_total_references=400,
        reference_relevance_threshold=0.35,
        max_reference_downloads=5,
        min_reference_value_score=0.55,
        require_reference_doi=True,
        reference_query="foundation papers",
        reference_sources=["openalex"],
    )).run()

    assert [call[0] if isinstance(call, tuple) else call for call in calls] == [
        "pipeline",
        "pdf",
        "references",
        "agent_input",
        "paper_reader",
        "domain_synth",
        "report",
    ]
    reference_service = calls[2][1]
    assert reference_service.manifest_path == tmp_path / "pdf.json"
    assert reference_service.out_dir == tmp_path / "run" / "results" / "references"
    assert reference_service.max_references_per_paper == 40
    assert reference_service.max_total_references == 400
    assert reference_service.relevance_threshold == 0.35
    assert reference_service.max_reference_downloads == 5
    assert reference_service.min_value_score == 0.55
    assert reference_service.require_doi_for_download is True
    assert reference_service.reference_query == "foundation papers"
    assert reference_service.metadata_sources == ["openalex"]
    assert outputs.references_dir == tmp_path / "run" / "results" / "references"


def test_survey_command_service_can_skip_agents(monkeypatch, tmp_path):
    calls = []

    class FakePipelineOutputs:
        download_manifest = tmp_path / "run" / "results" / "article_manifest.json"
        final_manifest = tmp_path / "run" / "results" / "classified_manifest.json"

    monkeypatch.setattr("litsurveygrp.pipeline.SurveyPipelineService.run", lambda self: calls.append("pipeline") or FakePipelineOutputs())
    monkeypatch.setattr("litsurveygrp.pipeline.TopPdfDownloadService.run", lambda self: calls.append("pdf") or {"manifest": tmp_path / "pdf.json"})
    monkeypatch.setattr("litsurveygrp.pipeline.AgentInputPreparer.run", lambda self: calls.append("agent_input") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.PaperReaderAgent.run", lambda self: calls.append("paper_reader") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.DomainSynthesizerAgent.run", lambda self: calls.append("domain_synth") or {})
    monkeypatch.setattr("litsurveygrp.pipeline.FinalSurveyReportBuilder.build", lambda self: calls.append("report") or {
        "markdown": tmp_path / "report.md",
        "html": tmp_path / "report.html",
    })

    SurveyCommandService(SurveyCommandConfig(out_dir=tmp_path / "run", run_agents=False)).run()

    assert calls == ["pipeline", "pdf", "agent_input", "report"]


def test_survey_command_cli_adapter_runs(monkeypatch, tmp_path):
    captured = {}

    class Args:
        out = str(tmp_path / "run")
        query = "AI in neuroscience"
        journal = None
        limit = 10
        per_journal_limit = None
        from_year = 2020
        to_year = 2026
        keyword = ["AI"]
        article_type = ["Article"]
        min_citations = 2
        sources = ["openalex"]
        request_interval = 1.5
        top_papers = 12
        top_domains = 4
        per_domain = 6
        download_workers = 3
        download_timeout = 9
        min_value_score = 0.4
        require_doi = True
        agent_provider = "dry-run"
        agent_model = "gpt-4.1-mini"
        agent_cache_dir = str(tmp_path / "cache")
        skip_agents = True
        no_extract_pdf_text = True
        max_text_chars = 5000
        title = "Survey"
        domain_rules = "rules.json"
        enrichment_workers = 4
        classification_workers = 3
        analyze_references = True
        max_references_per_paper = 40
        max_total_references = 400
        reference_relevance_threshold = 0.35
        max_reference_downloads = 5
        min_reference_value_score = 0.55
        require_reference_doi = True
        reference_query = "foundation papers"
        reference_sources = ["openalex"]
        clean_existing = True

    def fake_run(self):
        captured["config"] = self.config
        return None

    monkeypatch.setattr(SurveyCommandService, "run", fake_run)

    assert run_survey_from_args(Args()) == 0
    config = captured["config"]
    assert config.out_dir.name == "run"
    assert config.query == "AI in neuroscience"
    assert config.limit == 10
    assert config.keywords == ["AI"]
    assert config.metadata_sources == ["openalex"]
    assert config.top_papers == 12
    assert config.agent_cache_dir.name == "cache"
    assert config.run_agents is False
    assert config.extract_pdf_text is False
    assert config.domain_rules == "rules.json"
    assert config.enrichment_workers == 4
    assert config.classification_workers == 3
    assert config.analyze_references is True
    assert config.max_references_per_paper == 40
    assert config.max_total_references == 400
    assert config.reference_relevance_threshold == 0.35
    assert config.max_reference_downloads == 5
    assert config.min_reference_value_score == 0.55
    assert config.require_reference_doi is True
    assert config.reference_query == "foundation papers"
    assert config.reference_sources == ["openalex"]
    assert config.clean_existing is True

