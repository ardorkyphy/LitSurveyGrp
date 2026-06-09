# -*- coding: utf-8 -*-
"""Rank source papers by research value and download the top PDFs."""

import csv
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from litsurveygrp.manifest_io import ArticleManifestWriter, DownloadReportWriter
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pdf_utils import PdfDownloader
from litsurveygrp.analysis_paths import article_subdomain, major_domain_name
from litsurveygrp.research_stats import ResearchStatsWriter, extract_year, recommendation_type
from litsurveygrp.run_monitor import RunMonitor


@dataclass
class RankedPdfCandidate:
    """One source paper with PDF-download ranking metadata."""

    rank: int
    article: ArticleRecord
    research_value_score: float
    reason: str
    journal_tier: str
    eligible: bool
    eligibility_reason: str
    selected_for_download: bool = False


class TopPdfDownloadService:
    """Download PDFs for the highest-value papers in an existing manifest."""

    def __init__(
        self,
        manifest_path: Path,
        papers_dir: Path,
        results_dir: Path | None = None,
        top: int = 20,
        per_domain: int = 0,
        min_value_score: float | None = None,
        download_workers: int = 1,
        timeout: int = 15,
        require_doi: bool = False,
        skip_existing: bool = True,
        retry_oa_resolution: bool = True,
        output_manifest_name: str = "pdf_downloaded_manifest.json",
        ranking_name: str = "pdf_download_ranking.csv",
        report_name: str = "pdf_download_report.csv",
        summary_name: str = "pdf_download_summary.json",
        project_name: str = "",
        monitor: RunMonitor | None = None,
        downloader_cls=PdfDownloader,
    ):
        self.manifest_path = Path(manifest_path)
        self.papers_dir = Path(papers_dir)
        self.results_dir = Path(results_dir) if results_dir else self.manifest_path.parent
        self.top = max(0, int(top or 0))
        self.per_domain = max(0, int(per_domain or 0))
        self.min_value_score = min_value_score
        self.download_workers = max(1, int(download_workers or 1))
        self.timeout = timeout
        self.require_doi = require_doi
        self.skip_existing = skip_existing
        self.retry_oa_resolution = retry_oa_resolution
        self.output_manifest_name = output_manifest_name
        self.ranking_name = ranking_name
        self.report_name = report_name
        self.summary_name = summary_name
        self.major_domain = major_domain_name(project_name)
        self.monitor = monitor
        self.downloader_cls = downloader_cls
        self._worker_state = threading.local()

    def run(self) -> dict[str, Path]:
        articles = self.load_manifest()
        ranked = self.rank_articles(articles)
        selected = self.select_candidates(ranked)
        for candidate in selected:
            candidate.selected_for_download = True

        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.start_monitor(ranked, selected)
        self.write_ranking(ranked)
        try:
            self.download_selected(selected)
            self.write_ranking(ranked)

            outputs = {
                "manifest": ArticleManifestWriter(self.results_dir, self.output_manifest_name).write(articles),
                "ranking": self.results_dir / self.ranking_name,
                "download_report": DownloadReportWriter(self.results_dir, self.report_name).write(
                    [candidate.article for candidate in selected]
                ),
                "summary": self.write_summary(ranked, selected),
            }
            completed = sum(
                bool(candidate.article.pdf_status == "complete" and candidate.article.local_pdf_path)
                for candidate in selected
            )
            failed = sum(bool(candidate.article.pdf_status != "complete") for candidate in selected)
            self.update_monitor(
                processed=len(selected),
                total=len(selected),
                current_item="",
                metrics={"completed_pdfs": completed, "failed_pdfs": failed, "selected_for_download": len(selected)},
            )
            self.finish_monitor("completed", f"PDF download completed {completed} of {len(selected)} selected papers")
            return outputs
        except Exception as exc:
            self.finish_monitor("failed", f"PDF download failed: {exc}")
            raise

    def select_candidates(self, ranked: list[RankedPdfCandidate]) -> list[RankedPdfCandidate]:
        eligible = [candidate for candidate in ranked if candidate.eligible]
        if self.per_domain <= 0:
            return eligible[: self.top]
        grouped: dict[str, list[RankedPdfCandidate]] = {}
        for candidate in eligible:
            key = article_subdomain(candidate.article)
            grouped.setdefault(key, []).append(candidate)
        selected: list[RankedPdfCandidate] = []
        domain_groups = sorted(
            grouped.items(),
            key=lambda item: (
                -len(item[1]),
                -sum(int(candidate.article.citation_count or 0) for candidate in item[1]),
                item[0],
            ),
        )
        if self.top > 0:
            domain_groups = domain_groups[: self.top]
        for _, candidates in domain_groups:
            selected.extend(candidates[: self.per_domain])
        return selected

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def rank_articles(self, articles: list[ArticleRecord]) -> list[RankedPdfCandidate]:
        stats = ResearchStatsWriter(self.manifest_path, top_n=max(1, len(articles)))
        max_citations = max([int(article.citation_count or 0) for article in articles] or [0])
        candidates = []
        for article in articles:
            score, reason, tier = stats.paper_value(article, max_citations)
            eligible, eligibility_reason = self.pdf_download_eligibility(article, score)
            candidates.append(
                RankedPdfCandidate(
                    rank=0,
                    article=article,
                    research_value_score=score,
                    reason=reason,
                    journal_tier=tier,
                    eligible=eligible,
                    eligibility_reason=eligibility_reason,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                -candidate.research_value_score,
                -int(candidate.article.citation_count or 0),
                (candidate.article.title or "").lower(),
            )
        )
        for index, candidate in enumerate(candidates, start=1):
            candidate.rank = index
        return candidates

    def pdf_download_eligibility(self, article: ArticleRecord, score: float) -> tuple[bool, str]:
        if self.require_doi and not article.doi:
            return False, "missing_doi"
        if self.min_value_score is not None and score < self.min_value_score:
            return False, "below_min_value_score"
        if self.skip_existing and article.pdf_status == "complete" and article.local_pdf_path:
            return False, "already_complete"
        return True, "eligible"

    def download_selected(self, selected: list[RankedPdfCandidate]) -> None:
        if not selected:
            return
        completed = 0
        failed = 0
        if self.download_workers <= 1:
            for index, candidate in enumerate(selected, start=1):
                self.update_monitor(
                    processed=index - 1,
                    total=len(selected),
                    current_item=candidate.article.title,
                    metrics={"completed_pdfs": completed, "failed_pdfs": failed, "download_workers": self.download_workers},
                )
                self.download_one(candidate.article)
                if candidate.article.pdf_status == "complete" and candidate.article.local_pdf_path:
                    completed += 1
                else:
                    failed += 1
                self.update_monitor(
                    processed=index,
                    total=len(selected),
                    current_item=candidate.article.title,
                    metrics={"completed_pdfs": completed, "failed_pdfs": failed, "download_workers": self.download_workers},
                )
            return
        with ThreadPoolExecutor(max_workers=self.download_workers) as executor:
            futures = {
                executor.submit(self.download_one, candidate.article): candidate
                for candidate in selected
            }
            processed = 0
            for future in as_completed(futures):
                candidate = futures[future]
                future.result()
                processed += 1
                if candidate.article.pdf_status == "complete" and candidate.article.local_pdf_path:
                    completed += 1
                else:
                    failed += 1
                self.update_monitor(
                    processed=processed,
                    total=len(selected),
                    current_item=candidate.article.title,
                    metrics={"completed_pdfs": completed, "failed_pdfs": failed, "download_workers": self.download_workers},
                )

    def download_one(self, article: ArticleRecord) -> ArticleRecord:
        if self.retry_oa_resolution and article.pdf_resolution_status == "provider_no_pdf_url" and not article.pdf_url:
            article.pdf_resolution_status = ""
        downloader = getattr(self._worker_state, "downloader", None)
        if downloader is None:
            downloader = self.downloader_cls(self.papers_dir, timeout=self.timeout, domain_path_func=self.domain_path_for_article)
            self._worker_state.downloader = downloader
        return downloader.download(article)

    def domain_path_for_article(self, article: ArticleRecord) -> tuple[str, str]:
        return self.major_domain, article_subdomain(article)

    def write_ranking(self, ranked: list[RankedPdfCandidate]) -> Path:
        path = self.results_dir / self.ranking_name
        fields = [
            "rank",
            "selected_for_download",
            "eligible",
            "eligibility_reason",
            "recommendation_type",
            "title",
            "doi",
            "journal",
            "journal_tier",
            "year",
            "subdomain",
            "article_type",
            "citation_count",
            "citation_source",
            "research_value_score",
            "reason",
            "pdf_url",
            "local_pdf_path",
            "download_status",
            "pdf_status",
            "error",
        ]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for candidate in ranked:
                writer.writerow(self.ranking_row(candidate))
        return path

    def ranking_row(self, candidate: RankedPdfCandidate) -> dict:
        article = candidate.article
        return {
            "rank": candidate.rank,
            "selected_for_download": candidate.selected_for_download,
            "eligible": candidate.eligible,
            "eligibility_reason": candidate.eligibility_reason,
            "recommendation_type": recommendation_type(article),
            "title": article.title,
            "doi": article.doi,
            "journal": article.journal,
            "journal_tier": candidate.journal_tier,
            "year": extract_year(article.publish_date) or "",
            "subdomain": article.subdomain or "Other",
            "article_type": article.article_type or "Unknown",
            "citation_count": int(article.citation_count or 0),
            "citation_source": article.citation_source,
            "research_value_score": candidate.research_value_score,
            "reason": candidate.reason,
            "pdf_url": article.pdf_url,
            "local_pdf_path": str(article.local_pdf_path) if article.local_pdf_path else "",
            "download_status": article.download_status,
            "pdf_status": article.pdf_status,
            "error": article.error,
        }

    def write_summary(self, ranked: list[RankedPdfCandidate], selected: list[RankedPdfCandidate]) -> Path:
        path = self.results_dir / self.summary_name
        selected_articles = [candidate.article for candidate in selected]
        summary = {
            "manifest": str(self.manifest_path),
            "papers_dir": str(self.papers_dir),
            "major_domain": self.major_domain,
            "total_candidates": len(ranked),
            "eligible_candidates": sum(candidate.eligible for candidate in ranked),
            "requested_top_downloads": self.top,
            "requested_per_domain_downloads": self.per_domain,
            "selected_for_download": len(selected),
            "completed_pdfs": sum(
                bool(article.pdf_status == "complete" and article.local_pdf_path)
                for article in selected_articles
            ),
            "min_value_score": self.min_value_score,
            "require_doi": self.require_doi,
            "skip_existing": self.skip_existing,
            "download_workers": self.download_workers,
            "retry_oa_resolution": self.retry_oa_resolution,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
        return path

    def start_monitor(self, ranked: list[RankedPdfCandidate], selected: list[RankedPdfCandidate]) -> None:
        if not self.monitor:
            return
        self.monitor.start(
            "Top PDF download",
            "Downloading high-value PDFs for agent analysis",
            metrics={
                "manifest": str(self.manifest_path),
                "papers_dir": str(self.papers_dir),
                "total_candidates": len(ranked),
                "eligible_candidates": sum(candidate.eligible for candidate in ranked),
                "selected_for_download": len(selected),
                "top": self.top,
                "per_domain": self.per_domain,
                "download_workers": self.download_workers,
            },
        )
        self.update_monitor(
            processed=0,
            total=len(selected),
            current_item="",
            metrics={"completed_pdfs": 0, "failed_pdfs": 0, "selected_for_download": len(selected)},
        )

    def update_monitor(self, processed: int, total: int, current_item: str, metrics: dict | None = None) -> None:
        if self.monitor:
            self.monitor.update(
                stage="pdf_download",
                message="Downloading selected PDFs",
                processed=processed,
                total=total,
                current_item=current_item,
                metrics=metrics,
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def run_from_args(args) -> int:
    service = TopPdfDownloadService(
        manifest_path=Path(args.manifest),
        papers_dir=Path(args.papers_dir),
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        top=getattr(args, "top", 20),
        per_domain=getattr(args, "per_domain", 0),
        min_value_score=getattr(args, "min_value_score", None),
        download_workers=getattr(args, "download_workers", 8),
        timeout=getattr(args, "timeout", 15),
        require_doi=getattr(args, "require_doi", False),
        skip_existing=not getattr(args, "include_existing", False),
        retry_oa_resolution=not getattr(args, "no_retry_oa_resolution", False),
        output_manifest_name=getattr(args, "out_manifest_name", "pdf_downloaded_manifest.json"),
        monitor=RunMonitor(
            Path(getattr(args, "monitor_dir", "") or getattr(args, "results_dir", "") or Path(args.manifest).parent)
        ),
    )
    service.run()
    return 0
