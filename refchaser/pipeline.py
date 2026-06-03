# -*- coding: utf-8 -*-
"""End-to-end literature survey pipeline orchestration."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from refchaser.enrichment.metadata_enrichment import (
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_SOURCES,
    MetadataEnrichmentService,
)
from refchaser.filters import ArticleFilter
from refchaser.multi_journal_downloader import MultiJournalDownloadService, parse_journal_specs
from refchaser.paper_classifier import PaperClassificationService
from refchaser.research_stats import ResearchStatsWriter
from refchaser.visualization import ResearchDashboardWriter


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
            "pipeline_report": str(self.pipeline_report or ""),
        }


class SurveyPipelineService:
    """Run download, enrichment, classification, stats, and visualization in order."""

    def __init__(
        self,
        papers_dir: Path,
        results_dir: Path,
        journal_specs: list[str] | None = None,
        year: int | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        limit: int | None = None,
        per_journal_limit: int | None = None,
        download_timeout: int = 15,
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
        top_n: int = 20,
        clean_existing: bool = False,
    ):
        self.papers_dir = Path(papers_dir)
        self.results_dir = Path(results_dir)
        self.journal_specs = journal_specs or ["nature-aging"]
        self.year = year
        self.from_year = from_year
        self.to_year = to_year
        self.limit = limit
        self.per_journal_limit = per_journal_limit
        self.download_timeout = download_timeout
        self.pdf_only_candidates = pdf_only_candidates
        self.dry_run = dry_run
        self.article_filter = ArticleFilter(
            keywords=list(keywords or []),
            article_types=list(article_types or []),
            min_citations=min_citations,
            year=year,
            from_year=from_year,
            to_year=to_year,
            authors=list(authors or []),
            institutions=list(institutions or []),
        )
        self.filter_sources = filter_sources
        self.enrich_metadata = enrich_metadata
        self.metadata_sources = metadata_sources
        self.metadata_timeout = metadata_timeout
        self.request_interval = request_interval
        self.classify_papers = classify_papers
        self.copy_files = copy_files
        self.clean_classified = clean_classified
        self.sentence_model = sentence_model
        self.write_stats = write_stats
        self.write_visualization = write_visualization
        self.top_n = top_n
        self.clean_existing = clean_existing

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
        outputs.pipeline_report = self.write_pipeline_report(outputs)
        return outputs

    def _download(self, outputs: SurveyPipelineOutputs) -> Path:
        service = MultiJournalDownloadService(
            output_dir=self.papers_dir,
            results_dir=self.results_dir,
            journals=parse_journal_specs(self.journal_specs),
            year=self.year,
            from_year=self.from_year,
            to_year=self.to_year,
            limit=self.limit,
            per_journal_limit=self.per_journal_limit,
            dry_run=self.dry_run,
            manifest_name=outputs.download_manifest.name,
            report_name=outputs.download_report.name,
            download_timeout=self.download_timeout,
            pdf_only_candidates=self.pdf_only_candidates,
            article_filter=self.article_filter if self.article_filter.has_criteria() else None,
            prefilter_enricher=self.build_prefilter_enricher(),
        )
        service.run()
        return outputs.download_manifest

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
        report["year"] = self.year
        report["from_year"] = self.from_year
        report["to_year"] = self.to_year
        report["limit"] = self.limit
        report["per_journal_limit"] = self.per_journal_limit
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
    """CLI adapter for python -m refchaser run-survey."""
    service = SurveyPipelineService(
        papers_dir=Path(args.papers_dir),
        results_dir=Path(args.results_dir),
        journal_specs=getattr(args, "journal", None),
        year=getattr(args, "year", None),
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        limit=getattr(args, "limit", None),
        per_journal_limit=getattr(args, "per_journal_limit", None),
        download_timeout=getattr(args, "download_timeout", 15),
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
        top_n=getattr(args, "top", 20),
        clean_existing=getattr(args, "clean_existing", False),
    )
    service.run()
    return 0
