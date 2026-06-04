# -*- coding: utf-8 -*-
"""End-to-end literature survey pipeline orchestration."""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from litsurveygrp.enrichment.metadata_enrichment import (
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_SOURCES,
    MetadataEnrichmentService,
)
from litsurveygrp.filters import ArticleFilter
from litsurveygrp.multi_journal_downloader import JournalConfig, MultiJournalDownloadService, parse_journal_specs
from litsurveygrp.paper_classifier import PaperClassificationService
from litsurveygrp.reference_analysis import ReferenceAnalysisService
from litsurveygrp.research_stats import ResearchStatsWriter
from litsurveygrp.visualization import ResearchDashboardWriter


@dataclass
class SurveyPipelineConfig:
    """Configuration for one end-to-end literature survey run."""

    papers_dir: Path
    results_dir: Path
    journal_specs: list[str] | None = None
    query: str = ""
    year: int | None = None
    from_year: int | None = None
    to_year: int | None = None
    limit: int | None = None
    per_journal_limit: int | None = None
    download_timeout: int = 15
    download_workers: int = 1
    download_pdfs: bool = True
    pdf_only_candidates: bool = False
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
    classify_papers: bool = True
    copy_files: bool = True
    clean_classified: bool = True
    sentence_model: str = "allenai-specter"
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

    def __post_init__(self) -> None:
        self.papers_dir = Path(self.papers_dir)
        self.results_dir = Path(self.results_dir)
        if self.reference_out_dir is not None:
            self.reference_out_dir = Path(self.reference_out_dir)
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


@dataclass
class SurveyPipelineOutputs:
    """Paths produced by one pipeline run."""

    papers_dir: Path
    results_dir: Path
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
        download_pdfs: bool = True,
        pdf_only_candidates: bool = False,
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
        classify_papers: bool = True,
        copy_files: bool = True,
        clean_classified: bool = True,
        sentence_model: str = "allenai-specter",
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
                classify_papers=classify_papers,
                copy_files=copy_files,
                clean_classified=clean_classified,
                sentence_model=sentence_model,
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
            )
        self.article_filter = self.config.build_article_filter()
        self._sync_legacy_attributes()

    def _sync_legacy_attributes(self) -> None:
        """Expose historical attributes used by tests and external callers."""
        self.papers_dir = self.config.papers_dir
        self.results_dir = self.config.results_dir
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
        self.dry_run = self.config.dry_run
        self.filter_sources = self.config.filter_sources
        self.enrich_metadata = self.config.enrich_metadata
        self.metadata_sources = self.config.metadata_sources
        self.metadata_timeout = self.config.metadata_timeout
        self.request_interval = self.config.request_interval
        self.classify_papers = self.config.classify_papers
        self.copy_files = self.config.copy_files
        self.clean_classified = self.config.clean_classified
        self.sentence_model = self.config.sentence_model
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

    def run(self) -> SurveyPipelineOutputs:
        """Execute the full survey workflow and return output paths."""
        if self.clean_existing:
            self._clean_generated_dir(self.papers_dir)
            self._clean_generated_dir(self.results_dir)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        outputs = SurveyPipelineOutputs(
            papers_dir=self.papers_dir,
            results_dir=self.results_dir,
            download_manifest=self.results_dir / "article_manifest.json",
            download_report=self.results_dir / "download_report.csv",
        )
        current_manifest = self._download(outputs)
        if self.enrich_metadata:
            current_manifest = self._enrich(current_manifest, outputs)
        if self.classify_papers:
            current_manifest = self._classify(current_manifest, outputs)
        if self.write_stats:
            outputs.stats_dir = self.results_dir / "stats"
            ResearchStatsWriter(current_manifest, out_dir=outputs.stats_dir, top_n=self.top_n).write()
        if self.write_visualization:
            outputs.dashboard = ResearchDashboardWriter(
                current_manifest,
                out_dir=self.results_dir / "visualization",
                top_n=self.top_n,
            ).write()
        if self.analyze_references:
            outputs.references_dir = self.reference_out_dir or self.results_dir / "references"
            ReferenceAnalysisService(
                current_manifest,
                out_dir=outputs.references_dir,
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
        return outputs

    def _download(self, outputs: SurveyPipelineOutputs) -> Path:
        service = MultiJournalDownloadService(
            output_dir=self.papers_dir,
            results_dir=self.results_dir,
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
            article_filter=self.article_filter if self.article_filter.has_criteria() else None,
            prefilter_enricher=self.build_prefilter_enricher(),
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
            self.results_dir / "article_prefilter.json",
            sources=self.filter_sources or ["openalex", "crossref"],
            timeout=self.metadata_timeout,
            request_interval=self.request_interval,
        )

    def _enrich(self, manifest: Path, outputs: SurveyPipelineOutputs) -> Path:
        outputs.enriched_manifest = self.results_dir / "enriched_manifest.json"
        MetadataEnrichmentService(
            manifest,
            sources=self.metadata_sources or list(DEFAULT_SOURCES),
            output_path=outputs.enriched_manifest,
            timeout=self.metadata_timeout,
            request_interval=self.request_interval,
        ).run()
        return outputs.enriched_manifest

    def _classify(self, manifest: Path, outputs: SurveyPipelineOutputs) -> Path:
        outputs.classified_manifest = self.results_dir / "classified_manifest.json"
        PaperClassificationService(
            manifest,
            copy_files=self.copy_files,
            clean=self.clean_classified,
            output_dir=self.results_dir,
            organize_dir=self.papers_dir,
            sentence_model=self.sentence_model,
        ).run()
        return outputs.classified_manifest

    def write_pipeline_report(self, outputs: SurveyPipelineOutputs) -> Path:
        path = self.results_dir / "pipeline_report.json"
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
        report["filters"] = {
            "keywords": list(self.article_filter.keywords),
            "article_types": list(self.article_filter.article_types),
            "min_citations": self.article_filter.min_citations,
            "authors": list(self.article_filter.authors),
            "institutions": list(self.article_filter.institutions),
            "filter_sources": list(self.filter_sources or ["openalex", "crossref"]),
        }
        report["metadata_sources"] = self.metadata_sources or list(DEFAULT_SOURCES)
        report["request_interval"] = self.request_interval
        report["steps"] = {
            "download": True,
            "enrichment": self.enrich_metadata,
            "classification": self.classify_papers,
            "stats": self.write_stats,
            "visualization": self.write_visualization,
            "reference_analysis": self.analyze_references,
        }
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

    def _clean_generated_dir(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            return
        resolved = path.resolve()
        cwd = Path.cwd().resolve()
        if resolved in {Path(resolved.anchor), cwd, cwd.parent}:
            raise ValueError(f"refusing to clean unsafe generated directory: {path}")
        shutil.rmtree(resolved)


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp run-survey."""
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
        download_pdfs=getattr(args, "download_pdfs", True),
        pdf_only_candidates=getattr(args, "pdf_only_candidates", False),
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
        classify_papers=not getattr(args, "skip_classification", False),
        copy_files=not getattr(args, "move", False),
        sentence_model=getattr(args, "sentence_model", "allenai-specter"),
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
    )
    service.run()
    return 0

