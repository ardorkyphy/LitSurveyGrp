# -*- coding: utf-8 -*-
"""End-to-end literature survey pipeline orchestration."""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from agents.domain_synthesizer_agent import DomainSynthesizerAgent
from agents.llm_client import default_model_for_provider
from agents.paper_reader_agent import PaperReaderAgent
from litsurveygrp.agent_input import AgentInputPreparer
from litsurveygrp.enrichment.metadata_enrichment import (
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_SOURCES,
    MetadataEnrichmentService,
)
from litsurveygrp.final_report import FinalSurveyReportBuilder
from litsurveygrp.filters import ArticleFilter
from litsurveygrp.analysis_paths import major_domain_name, report_data_dir
from litsurveygrp.multi_journal_downloader import JournalConfig, MultiJournalDownloadService, parse_journal_specs
from litsurveygrp.paper_classifier import PaperClassificationService
from litsurveygrp.pdf_download_stage import TopPdfDownloadService
from litsurveygrp.reference_analysis import ReferenceAnalysisService
from litsurveygrp.research_stats import ResearchStatsWriter
from litsurveygrp.run_monitor import RunMonitor
from litsurveygrp.stage_control import (
    COMMAND_STAGES,
    CORE_STAGES,
    STAGE_AGENT_INPUT,
    STAGE_CLASSIFICATION,
    STAGE_DISCOVERY,
    STAGE_DOMAIN_SYNTHESIS,
    STAGE_ENRICHMENT,
    STAGE_FINAL_REPORT,
    STAGE_PAPER_AGENTS,
    STAGE_PDF_DOWNLOAD,
    STAGE_REFERENCE_ANALYSIS,
    STAGE_STATS,
    STAGE_VISUALIZATION,
    StageControl,
)
from litsurveygrp.visualization import ResearchDashboardWriter


@dataclass
class SurveyPipelineConfig:
    """Configuration for one end-to-end literature survey run."""

    papers_dir: Path
    results_dir: Path
    reports_dir: Path | None = None
    journal_specs: list[str] | None = None
    query: str = ""
    year: int | None = None
    from_year: int | None = None
    to_year: int | None = None
    limit: int | None = None
    per_journal_limit: int | None = None
    download_timeout: int = 15
    download_workers: int = 1
    download_pdfs: bool = False
    pdf_only_candidates: bool = False
    metadata_cache_dir: Path | None = None
    use_metadata_cache: bool = True
    dry_run: bool = False
    keywords: list[str] = field(default_factory=list)
    article_types: list[str] = field(default_factory=list)
    min_citations: int | None = None
    authors: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    filter_sources: list[str] | None = None
    enrich_metadata: bool = True
    metadata_sources: list[str] | None = None
    metadata_timeout: int = 15
    request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS
    enrichment_workers: int = 1
    classify_papers: bool = True
    copy_files: bool = True
    clean_classified: bool = True
    sentence_model: str = "allenai-specter"
    domain_rules: str = ""
    classification_workers: int = 1
    write_stats: bool = True
    write_visualization: bool = True
    analyze_references: bool = False
    reference_out_dir: Path | None = None
    max_references_per_paper: int | None = 50
    max_total_references: int | None = 1000
    reference_relevance_threshold: float = 0.30
    max_reference_downloads: int = 0
    min_reference_value_score: float = 0.45
    require_reference_doi: bool = False
    reference_query: str = ""
    reference_sources: list[str] | None = None
    top_n: int = 20
    clean_existing: bool = False
    stage_control: StageControl = field(default_factory=StageControl)

    def __post_init__(self) -> None:
        self.papers_dir = Path(self.papers_dir)
        self.results_dir = Path(self.results_dir)
        self.reports_dir = Path(self.reports_dir) if self.reports_dir else self.results_dir.parent / "reports"
        if self.reference_out_dir is not None:
            self.reference_out_dir = Path(self.reference_out_dir)
        if self.metadata_cache_dir is not None:
            self.metadata_cache_dir = Path(self.metadata_cache_dir)
        if self.stage_control is None:
            self.stage_control = StageControl()
        self.keywords = list(self.keywords or [])
        self.article_types = list(self.article_types or [])
        self.authors = list(self.authors or [])
        self.institutions = list(self.institutions or [])
        if self.journal_specs is None:
            self.journal_specs = [] if self.query else ["nature-aging"]

    def build_article_filter(self) -> ArticleFilter:
        """Build the reusable article filter from survey config."""
        return ArticleFilter(
            keywords=self.keywords,
            article_types=self.article_types,
            min_citations=self.min_citations,
            year=self.year,
            from_year=self.from_year,
            to_year=self.to_year,
            authors=self.authors,
            institutions=self.institutions,
        )

    @property
    def major_domain(self) -> str:
        return major_domain_name(self.query or ", ".join(self.journal_specs or []))

    @property
    def report_data_dir(self) -> Path:
        return report_data_dir(self.reports_dir, self.major_domain)


@dataclass
class SurveyPipelineOutputs:
    """Paths produced by one pipeline run."""

    papers_dir: Path
    results_dir: Path
    reports_dir: Path
    download_manifest: Path
    download_report: Path
    enriched_manifest: Path | None = None
    classified_manifest: Path | None = None
    stats_dir: Path | None = None
    dashboard: Path | None = None
    references_dir: Path | None = None
    pipeline_report: Path | None = None

    @property
    def final_manifest(self) -> Path:
        return self.classified_manifest or self.enriched_manifest or self.download_manifest

    def to_dict(self) -> dict:
        return {
            "papers_dir": str(self.papers_dir),
            "results_dir": str(self.results_dir),
            "reports_dir": str(self.reports_dir),
            "download_manifest": str(self.download_manifest),
            "download_report": str(self.download_report),
            "enriched_manifest": str(self.enriched_manifest or ""),
            "classified_manifest": str(self.classified_manifest or ""),
            "final_manifest": str(self.final_manifest),
            "stats_dir": str(self.stats_dir or ""),
            "dashboard": str(self.dashboard or ""),
            "references_dir": str(self.references_dir or ""),
            "pipeline_report": str(self.pipeline_report or ""),
        }


@dataclass
class SurveyCommandConfig:
    """User-facing end-to-end survey configuration."""

    out_dir: Path
    journal_specs: list[str] | None = None
    query: str = ""
    from_year: int | None = None
    to_year: int | None = None
    limit: int | None = None
    per_journal_limit: int | None = None
    keywords: list[str] = field(default_factory=list)
    article_types: list[str] = field(default_factory=list)
    min_citations: int | None = None
    metadata_sources: list[str] | None = None
    request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS
    enrichment_workers: int = 1
    top_papers: int = 30
    pdfs_per_domain: int = 0
    top_domains: int = 10
    per_domain: int = 30
    download_workers: int = 8
    download_timeout: int = 15
    min_value_score: float | None = None
    require_doi: bool = False
    agent_provider: str = "dry-run"
    agent_model: str = ""
    agent_base_url: str = ""
    agent_cache_dir: Path | None = None
    agent_workers: int = 1
    agent_input_mode: str = "evidence-chunks"
    agent_max_chunks_per_paper: int = 12
    agent_max_chunk_chars: int = 2200
    run_agents: bool = True
    extract_pdf_text: bool = True
    max_text_chars: int = 0
    report_title: str = ""
    domain_rules: str = ""
    classification_workers: int = 1
    analyze_references: bool = False
    max_references_per_paper: int | None = 50
    max_total_references: int | None = 1000
    reference_relevance_threshold: float = 0.30
    max_reference_downloads: int = 0
    min_reference_value_score: float = 0.45
    require_reference_doi: bool = False
    reference_query: str = ""
    reference_sources: list[str] | None = None
    clean_existing: bool = False
    stage_control: StageControl = field(default_factory=StageControl)

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.journal_specs = list(self.journal_specs or [])
        self.keywords = list(self.keywords or [])
        self.article_types = list(self.article_types or [])
        self.reference_sources = list(self.reference_sources or [])
        if self.stage_control is None:
            self.stage_control = StageControl()
        self.agent_model = self.agent_model or default_model_for_provider(self.agent_provider)
        self.pdfs_per_domain = max(0, int(self.pdfs_per_domain or 0))
        self.agent_workers = max(1, int(self.agent_workers or 1))
        if self.agent_input_mode not in {"evidence-chunks", "full-text"}:
            raise ValueError(f"unsupported agent input mode: {self.agent_input_mode}")
        self.agent_max_chunks_per_paper = max(1, int(self.agent_max_chunks_per_paper or 1))
        self.agent_max_chunk_chars = max(400, int(self.agent_max_chunk_chars or 2200))
        if self.agent_cache_dir is not None:
            self.agent_cache_dir = Path(self.agent_cache_dir)

    def stage_enabled(self, stage: str) -> bool:
        defaults = {
            STAGE_DISCOVERY: True,
            STAGE_ENRICHMENT: True,
            STAGE_CLASSIFICATION: True,
            STAGE_STATS: True,
            STAGE_VISUALIZATION: True,
            STAGE_PDF_DOWNLOAD: True,
            STAGE_REFERENCE_ANALYSIS: self.analyze_references,
            STAGE_AGENT_INPUT: True,
            STAGE_PAPER_AGENTS: self.run_agents,
            STAGE_DOMAIN_SYNTHESIS: self.run_agents,
            STAGE_FINAL_REPORT: True,
        }
        return self.stage_control.is_enabled(stage, defaults.get(stage, True))

    @property
    def papers_dir(self) -> Path:
        return self.out_dir / "papers"

    @property
    def results_dir(self) -> Path:
        return self.out_dir / "results"

    @property
    def reports_dir(self) -> Path:
        return self.out_dir / "reports"

    @property
    def major_domain(self) -> str:
        return major_domain_name(self.query or ", ".join(self.journal_specs))

    @property
    def report_data_dir(self) -> Path:
        return report_data_dir(self.reports_dir, self.major_domain)

    @property
    def agent_dir(self) -> Path:
        return self.results_dir / self.major_domain


@dataclass
class SurveyCommandOutputs:
    """Important outputs from the user-facing survey command."""

    out_dir: Path
    papers_dir: Path
    results_dir: Path
    agent_dir: Path
    article_manifest: Path
    classified_manifest: Path
    reports_dir: Path | None = None
    pdf_manifest: Path | None = None
    references_dir: Path | None = None
    markdown_report: Path | None = None
    html_report: Path | None = None

    @property
    def final_manifest(self) -> Path:
        return self.pdf_manifest or self.classified_manifest or self.article_manifest


class SurveyPipelineService:
    """Run download, enrichment, classification, stats, and visualization in order."""

    def __init__(
        self,
        papers_dir: Path | SurveyPipelineConfig,
        results_dir: Path | None = None,
        journal_specs: list[str] | None = None,
        query: str = "",
        year: int | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        limit: int | None = None,
        per_journal_limit: int | None = None,
        download_timeout: int = 15,
        download_workers: int = 1,
        download_pdfs: bool = False,
        pdf_only_candidates: bool = False,
        metadata_cache_dir: Path | None = None,
        use_metadata_cache: bool = True,
        dry_run: bool = False,
        keywords: list[str] | None = None,
        article_types: list[str] | None = None,
        min_citations: int | None = None,
        authors: list[str] | None = None,
        institutions: list[str] | None = None,
        filter_sources: list[str] | None = None,
        enrich_metadata: bool = True,
        metadata_sources: list[str] | None = None,
        metadata_timeout: int = 15,
        request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        enrichment_workers: int = 1,
        classify_papers: bool = True,
        copy_files: bool = True,
        clean_classified: bool = True,
        sentence_model: str = "allenai-specter",
        domain_rules: str = "",
        classification_workers: int = 1,
        write_stats: bool = True,
        write_visualization: bool = True,
        analyze_references: bool = False,
        reference_out_dir: Path | None = None,
        max_references_per_paper: int | None = 50,
        max_total_references: int | None = 1000,
        reference_relevance_threshold: float = 0.30,
        max_reference_downloads: int = 0,
        min_reference_value_score: float = 0.45,
        require_reference_doi: bool = False,
        reference_query: str = "",
        reference_sources: list[str] | None = None,
        top_n: int = 20,
        clean_existing: bool = False,
        stage_control: StageControl | None = None,
    ):
        if isinstance(papers_dir, SurveyPipelineConfig):
            self.config = papers_dir
        else:
            if results_dir is None:
                raise ValueError("results_dir is required when not passing SurveyPipelineConfig")
            self.config = SurveyPipelineConfig(
                papers_dir=Path(papers_dir),
                results_dir=Path(results_dir),
                journal_specs=journal_specs,
                query=query,
                year=year,
                from_year=from_year,
                to_year=to_year,
                limit=limit,
                per_journal_limit=per_journal_limit,
                download_timeout=download_timeout,
                download_workers=download_workers,
                download_pdfs=download_pdfs,
                pdf_only_candidates=pdf_only_candidates,
                metadata_cache_dir=metadata_cache_dir,
                use_metadata_cache=use_metadata_cache,
                dry_run=dry_run,
                keywords=list(keywords or []),
                article_types=list(article_types or []),
                min_citations=min_citations,
                authors=list(authors or []),
                institutions=list(institutions or []),
                filter_sources=filter_sources,
                enrich_metadata=enrich_metadata,
                metadata_sources=metadata_sources,
                metadata_timeout=metadata_timeout,
                request_interval=request_interval,
                enrichment_workers=enrichment_workers,
                classify_papers=classify_papers,
                copy_files=copy_files,
                clean_classified=clean_classified,
                sentence_model=sentence_model,
                domain_rules=domain_rules,
                classification_workers=classification_workers,
                write_stats=write_stats,
                write_visualization=write_visualization,
                analyze_references=analyze_references,
                reference_out_dir=reference_out_dir,
                max_references_per_paper=max_references_per_paper,
                max_total_references=max_total_references,
                reference_relevance_threshold=reference_relevance_threshold,
                max_reference_downloads=max_reference_downloads,
                min_reference_value_score=min_reference_value_score,
                require_reference_doi=require_reference_doi,
                reference_query=reference_query,
                reference_sources=reference_sources,
                top_n=top_n,
                clean_existing=clean_existing,
                stage_control=stage_control or StageControl(),
            )
        self.article_filter = self.config.build_article_filter()
        self.monitor = RunMonitor(self.report_overview_dir())
        self._sync_legacy_attributes()

    def _sync_legacy_attributes(self) -> None:
        """Expose historical attributes used by tests and external callers."""
        self.papers_dir = self.config.papers_dir
        self.results_dir = self.config.results_dir
        self.reports_dir = self.config.reports_dir
        self.query = self.config.query
        self.journal_specs = self.config.journal_specs
        self.year = self.config.year
        self.from_year = self.config.from_year
        self.to_year = self.config.to_year
        self.limit = self.config.limit
        self.per_journal_limit = self.config.per_journal_limit
        self.download_timeout = self.config.download_timeout
        self.download_workers = self.config.download_workers
        self.download_pdfs = self.config.download_pdfs
        self.pdf_only_candidates = self.config.pdf_only_candidates
        self.metadata_cache_dir = self.config.metadata_cache_dir
        self.use_metadata_cache = self.config.use_metadata_cache
        self.dry_run = self.config.dry_run
        self.filter_sources = self.config.filter_sources
        self.enrich_metadata = self.config.enrich_metadata
        self.metadata_sources = self.config.metadata_sources
        self.metadata_timeout = self.config.metadata_timeout
        self.request_interval = self.config.request_interval
        self.enrichment_workers = self.config.enrichment_workers
        self.classify_papers = self.config.classify_papers
        self.copy_files = self.config.copy_files
        self.clean_classified = self.config.clean_classified
        self.sentence_model = self.config.sentence_model
        self.domain_rules = self.config.domain_rules
        self.classification_workers = self.config.classification_workers
        self.write_stats = self.config.write_stats
        self.write_visualization = self.config.write_visualization
        self.analyze_references = self.config.analyze_references
        self.reference_out_dir = self.config.reference_out_dir
        self.max_references_per_paper = self.config.max_references_per_paper
        self.max_total_references = self.config.max_total_references
        self.reference_relevance_threshold = self.config.reference_relevance_threshold
        self.max_reference_downloads = self.config.max_reference_downloads
        self.min_reference_value_score = self.config.min_reference_value_score
        self.require_reference_doi = self.config.require_reference_doi
        self.reference_query = self.config.reference_query
        self.reference_sources = self.config.reference_sources
        self.top_n = self.config.top_n
        self.clean_existing = self.config.clean_existing
        self.stage_control = self.config.stage_control

    def run(self) -> SurveyPipelineOutputs:
        """Execute the full survey workflow and return output paths."""
        if self.clean_existing:
            self._clean_generated_dir(self.papers_dir)
            self._clean_generated_dir(self.results_dir)
            self._clean_generated_dir(self.reports_dir)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.report_overview_dir().mkdir(parents=True, exist_ok=True)
        self.monitor.start(
            "LitSurveyGrp survey pipeline",
            "Running literature survey workflow",
            metrics={
                "journals": ", ".join(self.journal_specs or []),
                "query": self.query,
                "download_pdfs": self.download_pdfs,
                "metadata_cache_dir": str(self.effective_metadata_cache_dir()),
                "metadata_sources": ", ".join(self.metadata_sources or list(DEFAULT_SOURCES)),
                "enrichment_workers": self.enrichment_workers,
                "classification_workers": self.classification_workers,
            },
        )

        outputs = SurveyPipelineOutputs(
            papers_dir=self.papers_dir,
            results_dir=self.results_dir,
            reports_dir=self.reports_dir,
            download_manifest=self.report_overview_dir() / "article_manifest.json",
            download_report=self.report_overview_dir() / "download_report.csv",
        )
        if self.stage_enabled(STAGE_DISCOVERY):
            current_manifest = self._download(outputs)
        else:
            current_manifest = outputs.download_manifest
            self.monitor.update("download", "Paper discovery skipped", current_item=str(current_manifest))
        if self.stage_enabled(STAGE_ENRICHMENT):
            current_manifest = self._enrich(current_manifest, outputs)
        if self.stage_enabled(STAGE_CLASSIFICATION):
            current_manifest = self._classify(current_manifest, outputs)
        if self.stage_enabled(STAGE_STATS):
            self.monitor.update("stats", "Writing research statistics", current_item=str(current_manifest))
            outputs.stats_dir = self.report_overview_dir() / "stats"
            ResearchStatsWriter(current_manifest, out_dir=outputs.stats_dir, top_n=self.top_n).write()
        if self.stage_enabled(STAGE_VISUALIZATION):
            self.monitor.update("visualize", "Writing offline research dashboard", current_item=str(current_manifest))
            outputs.dashboard = ResearchDashboardWriter(
                current_manifest,
                out_dir=self.report_overview_dir() / "visualization",
                top_n=self.top_n,
            ).write()
        if self.stage_enabled(STAGE_REFERENCE_ANALYSIS):
            self.monitor.update("references", "Analyzing cited references", current_item=str(current_manifest))
            outputs.references_dir = self.reference_out_dir or self.report_overview_dir() / "references"
            ReferenceAnalysisService(
                current_manifest,
                out_dir=outputs.references_dir,
                papers_dir=self.papers_dir,
                project_name=self.query or ", ".join(self.journal_specs or []),
                max_references_per_paper=self.max_references_per_paper,
                max_total_references=self.max_total_references,
                relevance_threshold=self.reference_relevance_threshold,
                max_reference_downloads=self.max_reference_downloads,
                min_value_score=self.min_reference_value_score,
                require_doi_for_download=self.require_reference_doi,
                reference_query=self.reference_query,
                metadata_sources=self.reference_sources,
                metadata_timeout=self.metadata_timeout,
                request_interval=self.request_interval,
                sentence_model=self.sentence_model,
            ).run()
        outputs.pipeline_report = self.write_pipeline_report(outputs)
        self.monitor.finish("completed", f"Pipeline finished: {outputs.final_manifest}")
        return outputs

    def stage_enabled(self, stage: str) -> bool:
        defaults = {
            STAGE_DISCOVERY: True,
            STAGE_ENRICHMENT: self.enrich_metadata,
            STAGE_CLASSIFICATION: self.classify_papers,
            STAGE_STATS: self.write_stats,
            STAGE_VISUALIZATION: self.write_visualization,
            STAGE_REFERENCE_ANALYSIS: self.analyze_references,
        }
        return self.stage_control.is_enabled(stage, defaults.get(stage, True))

    def _download(self, outputs: SurveyPipelineOutputs) -> Path:
        self.monitor.update("download", "Collecting paper records", current_item=", ".join(self.journal_specs or []))
        service = MultiJournalDownloadService(
            output_dir=self.papers_dir,
            results_dir=outputs.download_manifest.parent,
            journals=self.build_journal_configs(),
            year=self.year,
            from_year=self.from_year,
            to_year=self.to_year,
            limit=self.limit,
            per_journal_limit=self.per_journal_limit,
            dry_run=self.dry_run,
            manifest_name=outputs.download_manifest.name,
            report_name=outputs.download_report.name,
            download_timeout=self.download_timeout,
            download_workers=self.download_workers,
            download_pdfs=self.download_pdfs,
            pdf_only_candidates=self.pdf_only_candidates,
            metadata_cache_dir=self.effective_metadata_cache_dir(),
            use_metadata_cache=self.use_metadata_cache,
            article_filter=self.article_filter if self.article_filter.has_criteria() else None,
            prefilter_enricher=self.build_prefilter_enricher(),
            monitor=self.monitor,
        )
        service.run()
        return outputs.download_manifest

    def build_journal_configs(self):
        if self.journal_specs:
            return parse_journal_specs(self.journal_specs)
        if self.query:
            return [JournalConfig(name=f"OpenAlex search: {self.query}", provider="openalex-search", query=self.query)]
        return parse_journal_specs(["nature-aging"])

    def build_prefilter_enricher(self):
        if not self.article_filter.needs_citation_count():
            return None
        return MetadataEnrichmentService(
            self.report_overview_dir() / "article_prefilter.json",
            sources=self.filter_sources or ["openalex", "crossref"],
            timeout=self.metadata_timeout,
            request_interval=self.request_interval,
            workers=self.enrichment_workers,
        )

    def _enrich(self, manifest: Path, outputs: SurveyPipelineOutputs) -> Path:
        self.monitor.update("enrich", "Starting metadata enrichment", current_item=str(manifest))
        outputs.enriched_manifest = self.report_overview_dir() / "enriched_manifest.json"
        MetadataEnrichmentService(
            manifest,
            sources=self.metadata_sources or list(DEFAULT_SOURCES),
            output_path=outputs.enriched_manifest,
            timeout=self.metadata_timeout,
            request_interval=self.request_interval,
            workers=self.enrichment_workers,
            monitor=self.monitor,
        ).run()
        return outputs.enriched_manifest

    def _classify(self, manifest: Path, outputs: SurveyPipelineOutputs) -> Path:
        self.monitor.update("classify", "Classifying papers into research topics", current_item=str(manifest))
        outputs.classified_manifest = self.report_overview_dir() / "classified_manifest.json"
        PaperClassificationService(
            manifest,
            copy_files=self.copy_files,
            clean=self.clean_classified,
            output_dir=self.report_overview_dir(),
            organize_dir=self.papers_dir,
            sentence_model=self.sentence_model,
            domain_rules=self.domain_rules,
            classification_workers=self.classification_workers,
        ).run()
        return outputs.classified_manifest

    def write_pipeline_report(self, outputs: SurveyPipelineOutputs) -> Path:
        path = self.report_overview_dir() / "pipeline_report.json"
        report = outputs.to_dict()
        report["journals"] = list(self.journal_specs)
        report["query"] = self.query
        report["year"] = self.year
        report["from_year"] = self.from_year
        report["to_year"] = self.to_year
        report["limit"] = self.limit
        report["per_journal_limit"] = self.per_journal_limit
        report["download_workers"] = self.download_workers
        report["download_pdfs"] = self.download_pdfs
        report["collection_mode"] = "download_pdfs" if self.download_pdfs else "metadata_only"
        report["metadata_cache"] = {
            "enabled": self.use_metadata_cache,
            "dir": str(self.effective_metadata_cache_dir()),
        }
        report["filters"] = {
            "keywords": list(self.article_filter.keywords),
            "article_types": list(self.article_filter.article_types),
            "min_citations": self.article_filter.min_citations,
            "authors": list(self.article_filter.authors),
            "institutions": list(self.article_filter.institutions),
            "filter_sources": list(self.filter_sources or ["openalex", "crossref"]),
        }
        report["metadata_sources"] = self.metadata_sources or list(DEFAULT_SOURCES)
        report["domain_rules"] = self.domain_rules
        report["request_interval"] = self.request_interval
        report["enrichment_workers"] = self.enrichment_workers
        report["classification_workers"] = self.classification_workers
        report["steps"] = {
            "download": self.stage_enabled(STAGE_DISCOVERY),
            STAGE_ENRICHMENT: self.stage_enabled(STAGE_ENRICHMENT),
            STAGE_CLASSIFICATION: self.stage_enabled(STAGE_CLASSIFICATION),
            STAGE_STATS: self.stage_enabled(STAGE_STATS),
            STAGE_VISUALIZATION: self.stage_enabled(STAGE_VISUALIZATION),
            STAGE_REFERENCE_ANALYSIS: self.stage_enabled(STAGE_REFERENCE_ANALYSIS),
        }
        report["stage_control"] = self.stage_control.to_dict()
        report["reference_analysis"] = {
            "max_references_per_paper": self.max_references_per_paper,
            "max_total_references": self.max_total_references,
            "reference_relevance_threshold": self.reference_relevance_threshold,
            "max_reference_downloads": self.max_reference_downloads,
            "min_reference_value_score": self.min_reference_value_score,
            "require_reference_doi": self.require_reference_doi,
            "reference_sources": self.reference_sources,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        return path

    def report_overview_dir(self) -> Path:
        return self.config.report_data_dir

    def effective_metadata_cache_dir(self) -> Path:
        env_dir = os.environ.get("LITSURVEYGRP_METADATA_CACHE_DIR", "").strip()
        return self.metadata_cache_dir or (Path(env_dir) if env_dir else self.report_overview_dir() / "metadata_cache")

    def _clean_generated_dir(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            return
        resolved = path.resolve()
        cwd = Path.cwd().resolve()
        if resolved in {Path(resolved.anchor), cwd, cwd.parent}:
            raise ValueError(f"refusing to clean unsafe generated directory: {path}")
        shutil.rmtree(resolved)


class SurveyCommandService:
    """Run the core product workflow: metadata, stats, top PDFs, agents, report."""

    def __init__(self, config: SurveyCommandConfig):
        self.config = config
        self.monitor = RunMonitor(config.report_data_dir)

    def run(self) -> SurveyCommandOutputs:
        config = self.config
        self.monitor.start(
            "LitSurveyGrp survey",
            "Running full survey workflow",
            metrics={
                "query": config.query,
                "papers_dir": str(config.papers_dir),
                "results_dir": str(config.results_dir),
                "reports_dir": str(config.reports_dir),
                "download_workers": config.download_workers,
                "agent_workers": config.agent_workers,
            },
        )
        try:
            pipeline_service = SurveyPipelineService(
                papers_dir=config.papers_dir,
                results_dir=config.results_dir,
                journal_specs=config.journal_specs or None,
                query=config.query,
                from_year=config.from_year,
                to_year=config.to_year,
                limit=config.limit,
                per_journal_limit=config.per_journal_limit,
                download_timeout=config.download_timeout,
                download_workers=config.download_workers,
                download_pdfs=False,
                keywords=config.keywords,
                article_types=config.article_types,
                min_citations=config.min_citations,
                metadata_sources=config.metadata_sources,
                request_interval=config.request_interval,
                enrichment_workers=config.enrichment_workers,
                analyze_references=False,
                top_n=config.top_papers,
                clean_existing=config.clean_existing,
                domain_rules=config.domain_rules,
                classification_workers=config.classification_workers,
                stage_control=config.stage_control,
            )
            pipeline_service.monitor = self.monitor.child("metadata_pipeline")
            pipeline_outputs = pipeline_service.run()

            pdf_manifest = pipeline_outputs.final_manifest
            if config.stage_enabled(STAGE_PDF_DOWNLOAD):
                pdf_outputs = TopPdfDownloadService(
                    manifest_path=pipeline_outputs.final_manifest,
                    papers_dir=config.papers_dir,
                    results_dir=config.report_data_dir,
                    top=config.top_domains if config.pdfs_per_domain > 0 else config.top_papers,
                    per_domain=config.pdfs_per_domain,
                    min_value_score=config.min_value_score,
                    download_workers=config.download_workers,
                    timeout=config.download_timeout,
                    require_doi=config.require_doi,
                    project_name=config.query or ", ".join(config.journal_specs),
                    monitor=self.monitor.child("pdf_download"),
                ).run()
                pdf_manifest = pdf_outputs["manifest"]
            else:
                self.monitor.update("pdf_download", "PDF download stage skipped", current_item=str(pdf_manifest))

            references_dir = None
            if config.stage_enabled(STAGE_REFERENCE_ANALYSIS):
                references_dir = config.report_data_dir / "references"
                self.monitor.update("references", "Analyzing cited references", current_item=str(pdf_manifest))
                ReferenceAnalysisService(
                    pdf_manifest,
                    out_dir=references_dir,
                    papers_dir=config.papers_dir,
                    project_name=config.query or ", ".join(config.journal_specs),
                    max_references_per_paper=config.max_references_per_paper,
                    max_total_references=config.max_total_references,
                    relevance_threshold=config.reference_relevance_threshold,
                    max_reference_downloads=config.max_reference_downloads,
                    min_value_score=config.min_reference_value_score,
                    require_doi_for_download=config.require_reference_doi,
                    reference_query=config.reference_query,
                    metadata_sources=config.reference_sources or None,
                    metadata_timeout=config.download_timeout,
                    request_interval=config.request_interval,
                ).run()

            if config.stage_enabled(STAGE_AGENT_INPUT):
                AgentInputPreparer(
                    manifest_path=pdf_manifest,
                    out_dir=config.agent_dir,
                    papers_dir=config.papers_dir,
                    results_dir=config.results_dir,
                    reports_dir=config.reports_dir,
                    top_domains=config.top_domains,
                    per_domain=config.per_domain,
                    selection="top-downloaded-pdfs",
                    top_papers=config.top_papers if config.pdfs_per_domain <= 0 else max(config.top_papers, config.pdfs_per_domain * max(config.top_domains, 1)),
                    copy_pdfs=True,
                    extract_pdf_text=config.extract_pdf_text,
                    max_text_chars=config.max_text_chars,
                    project_name=config.query or ", ".join(config.journal_specs),
                    monitor=self.monitor.child("agent_input"),
                ).run()
            else:
                self.monitor.update("agent_input", "Agent input preparation skipped", current_item=str(pdf_manifest))

            if config.stage_enabled(STAGE_PAPER_AGENTS):
                PaperReaderAgent(
                    input_dir=config.agent_dir,
                    results_dir=config.results_dir,
                    reports_dir=config.reports_dir,
                    provider=config.agent_provider,
                    model=config.agent_model,
                    cache_dir=config.agent_cache_dir,
                    base_url=config.agent_base_url,
                    workers=config.agent_workers,
                    input_mode=config.agent_input_mode,
                    max_chunks_per_paper=config.agent_max_chunks_per_paper,
                    max_chunk_chars=config.agent_max_chunk_chars,
                    monitor=self.monitor.child("paper_reader_agent"),
                ).run()
            if config.stage_enabled(STAGE_DOMAIN_SYNTHESIS):
                DomainSynthesizerAgent(
                    input_dir=config.agent_dir,
                    results_dir=config.results_dir,
                    reports_dir=config.reports_dir,
                    provider=config.agent_provider,
                    model=config.agent_model,
                    cache_dir=config.agent_cache_dir,
                    base_url=config.agent_base_url,
                    monitor=self.monitor.child("domain_synthesizer_agent"),
                ).run()

            report_outputs = {"markdown": None, "html": None}
            if config.stage_enabled(STAGE_FINAL_REPORT):
                self.monitor.update("final_report", "Building final survey report")
                report_outputs = FinalSurveyReportBuilder(
                    results_dir=config.results_dir,
                    agent_dir=config.agent_dir,
                    reports_dir=config.reports_dir,
                    title=config.report_title,
                ).build()
                self.monitor.finish("completed", f"Survey completed: {report_outputs['html']}")
            else:
                self.monitor.finish("completed", f"Survey completed: {pdf_manifest}")
        except Exception as exc:
            self.monitor.finish("failed", f"Survey failed: {exc}")
            raise

        return SurveyCommandOutputs(
            out_dir=config.out_dir,
            papers_dir=config.papers_dir,
            results_dir=config.results_dir,
            agent_dir=config.agent_dir,
            reports_dir=config.reports_dir,
            article_manifest=pipeline_outputs.download_manifest,
            classified_manifest=pipeline_outputs.final_manifest,
            pdf_manifest=pdf_manifest,
            references_dir=references_dir,
            markdown_report=report_outputs["markdown"],
            html_report=report_outputs["html"],
        )


SURVEY_PRESETS = {
    "fast": {
        "top_papers": 10,
        "pdfs_per_domain": 0,
        "top_domains": 5,
        "per_domain": 10,
        "download_workers": 8,
        "agent_workers": 1,
        "agent_input_mode": "evidence-chunks",
        "agent_max_chunks_per_paper": 8,
        "agent_max_chunk_chars": 1800,
    },
    "balanced": {
        "top_papers": 30,
        "pdfs_per_domain": 0,
        "top_domains": 10,
        "per_domain": 30,
        "download_workers": 8,
        "agent_workers": 1,
        "agent_input_mode": "evidence-chunks",
        "agent_max_chunks_per_paper": 12,
        "agent_max_chunk_chars": 2200,
    },
    "full": {
        "top_papers": 30,
        "pdfs_per_domain": 30,
        "top_domains": 10,
        "per_domain": 30,
        "download_workers": 8,
        "agent_workers": 2,
        "agent_input_mode": "evidence-chunks",
        "agent_max_chunks_per_paper": 14,
        "agent_max_chunk_chars": 2400,
    },
    "metadata": {
        "top_papers": 0,
        "pdfs_per_domain": 0,
        "top_domains": 10,
        "per_domain": 30,
        "download_workers": 8,
        "agent_workers": 1,
        "agent_input_mode": "evidence-chunks",
        "agent_max_chunks_per_paper": 12,
        "agent_max_chunk_chars": 2200,
    },
}


def survey_arg(args, name: str, default=None):
    value = getattr(args, name, None)
    return default if value is None else value


def run_survey_from_args(args) -> int:
    """CLI adapter for the simplified lsg survey command."""
    preset = dict(SURVEY_PRESETS.get(getattr(args, "preset", "balanced"), SURVEY_PRESETS["balanced"]))
    shared_workers = getattr(args, "workers", None)
    pdfs = getattr(args, "pdfs", None)
    domains = getattr(args, "domains", None)
    papers_per_domain = getattr(args, "papers_per_domain", None)
    model_provider = getattr(args, "model_provider", None)
    model = getattr(args, "model", None)
    skipped_stages = list(getattr(args, "skip_stage", None) or [])
    if getattr(args, "skip_agents", False):
        skipped_stages.extend([STAGE_PAPER_AGENTS, STAGE_DOMAIN_SYNTHESIS])
    stage_control = StageControl.from_values(
        disabled=skipped_stages,
        modes=getattr(args, "stage_mode", None) or [],
        allowed=COMMAND_STAGES,
    )
    config = SurveyCommandConfig(
        out_dir=Path(args.out),
        journal_specs=getattr(args, "journal", None),
        query=getattr(args, "query", ""),
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        limit=getattr(args, "limit", None),
        per_journal_limit=getattr(args, "per_journal_limit", None),
        keywords=getattr(args, "keyword", None) or [],
        article_types=getattr(args, "article_type", None) or [],
        min_citations=getattr(args, "min_citations", None),
        metadata_sources=getattr(args, "sources", None),
        request_interval=survey_arg(args, "request_interval", DEFAULT_REQUEST_INTERVAL_SECONDS),
        enrichment_workers=survey_arg(args, "enrichment_workers", 1),
        top_papers=survey_arg(args, "top_papers", 0 if pdfs == 0 else preset["top_papers"]),
        pdfs_per_domain=survey_arg(args, "pdfs_per_domain", pdfs if pdfs is not None else preset["pdfs_per_domain"]),
        top_domains=survey_arg(args, "top_domains", domains if domains is not None else preset["top_domains"]),
        per_domain=survey_arg(args, "per_domain", papers_per_domain if papers_per_domain is not None else preset["per_domain"]),
        download_workers=survey_arg(args, "download_workers", shared_workers if shared_workers is not None else preset["download_workers"]),
        download_timeout=getattr(args, "download_timeout", 15),
        min_value_score=getattr(args, "min_value_score", None),
        require_doi=getattr(args, "require_doi", False),
        agent_provider=survey_arg(args, "agent_provider", model_provider or "dry-run"),
        agent_model=survey_arg(args, "agent_model", model or ""),
        agent_base_url=getattr(args, "agent_base_url", ""),
        agent_cache_dir=Path(args.agent_cache_dir) if getattr(args, "agent_cache_dir", None) else None,
        agent_workers=survey_arg(args, "agent_workers", shared_workers if shared_workers is not None else preset["agent_workers"]),
        agent_input_mode=survey_arg(args, "agent_input_mode", preset["agent_input_mode"]),
        agent_max_chunks_per_paper=survey_arg(args, "agent_max_chunks_per_paper", preset["agent_max_chunks_per_paper"]),
        agent_max_chunk_chars=survey_arg(args, "agent_max_chunk_chars", preset["agent_max_chunk_chars"]),
        run_agents=not getattr(args, "skip_agents", False),
        extract_pdf_text=not getattr(args, "no_extract_pdf_text", False),
        max_text_chars=getattr(args, "max_text_chars", 0),
        report_title=getattr(args, "title", ""),
        domain_rules=getattr(args, "domain_rules", ""),
        classification_workers=survey_arg(args, "classification_workers", 1),
        analyze_references=getattr(args, "analyze_references", False),
        max_references_per_paper=getattr(args, "max_references_per_paper", 50),
        max_total_references=getattr(args, "max_total_references", 1000),
        reference_relevance_threshold=getattr(args, "reference_relevance_threshold", 0.30),
        max_reference_downloads=getattr(args, "max_reference_downloads", 0),
        min_reference_value_score=getattr(args, "min_reference_value_score", 0.45),
        require_reference_doi=getattr(args, "require_reference_doi", False),
        reference_query=getattr(args, "reference_query", ""),
        reference_sources=getattr(args, "reference_sources", None),
        clean_existing=getattr(args, "clean_existing", False),
        stage_control=stage_control,
    )
    SurveyCommandService(config).run()
    return 0


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp run-survey."""
    skipped_stages = list(getattr(args, "skip_stage", None) or [])
    if getattr(args, "skip_enrichment", False):
        skipped_stages.append(STAGE_ENRICHMENT)
    if getattr(args, "skip_classification", False):
        skipped_stages.append(STAGE_CLASSIFICATION)
    if getattr(args, "skip_stats", False):
        skipped_stages.append(STAGE_STATS)
    if getattr(args, "skip_visualization", False):
        skipped_stages.append(STAGE_VISUALIZATION)
    stage_control = StageControl.from_values(
        disabled=skipped_stages,
        modes=getattr(args, "stage_mode", None) or [],
        allowed=CORE_STAGES,
    )
    service = SurveyPipelineService(
        papers_dir=Path(args.papers_dir),
        results_dir=Path(args.results_dir),
        journal_specs=getattr(args, "journal", None),
        query=getattr(args, "query", ""),
        year=getattr(args, "year", None),
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        limit=getattr(args, "limit", None),
        per_journal_limit=getattr(args, "per_journal_limit", None),
        download_timeout=getattr(args, "download_timeout", 15),
        download_workers=getattr(args, "download_workers", 1),
        download_pdfs=getattr(args, "download_pdfs", False),
        pdf_only_candidates=getattr(args, "pdf_only_candidates", False),
        metadata_cache_dir=Path(args.metadata_cache_dir) if getattr(args, "metadata_cache_dir", None) else None,
        use_metadata_cache=not getattr(args, "no_metadata_cache", False),
        dry_run=getattr(args, "dry_run", False),
        keywords=getattr(args, "keyword", None),
        article_types=getattr(args, "article_type", None),
        min_citations=getattr(args, "min_citations", None),
        authors=getattr(args, "author", None),
        institutions=getattr(args, "institution", None),
        filter_sources=getattr(args, "filter_sources", None),
        enrich_metadata=not getattr(args, "skip_enrichment", False),
        metadata_sources=getattr(args, "sources", None),
        metadata_timeout=getattr(args, "metadata_timeout", 15),
        request_interval=getattr(args, "request_interval", DEFAULT_REQUEST_INTERVAL_SECONDS),
        enrichment_workers=getattr(args, "enrichment_workers", 1),
        classify_papers=not getattr(args, "skip_classification", False),
        copy_files=not getattr(args, "move", False),
        sentence_model=getattr(args, "sentence_model", "allenai-specter"),
        domain_rules=getattr(args, "domain_rules", ""),
        classification_workers=getattr(args, "classification_workers", 1),
        write_stats=not getattr(args, "skip_stats", False),
        write_visualization=not getattr(args, "skip_visualization", False),
        analyze_references=getattr(args, "analyze_references", False),
        reference_out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        max_references_per_paper=getattr(args, "max_references_per_paper", 50),
        max_total_references=getattr(args, "max_total_references", 1000),
        reference_relevance_threshold=getattr(args, "reference_relevance_threshold", 0.30),
        max_reference_downloads=getattr(args, "max_reference_downloads", 0),
        min_reference_value_score=getattr(args, "min_reference_value_score", 0.45),
        require_reference_doi=getattr(args, "require_reference_doi", False),
        reference_query=getattr(args, "reference_query", ""),
        reference_sources=getattr(args, "reference_sources", None),
        top_n=getattr(args, "top", 20),
        clean_existing=getattr(args, "clean_existing", False),
        stage_control=stage_control,
    )
    service.run()
    return 0

