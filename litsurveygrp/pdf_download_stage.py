# -*- coding: utf-8 -*-
"""Rank source papers by research value and download the top PDFs."""

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from litsurveygrp.manifest_io import ArticleManifestWriter, DownloadReportWriter
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pdf_utils import PdfDownloader
from litsurveygrp.research_stats import ResearchStatsWriter, extract_year, recommendation_type


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
        downloader_cls=PdfDownloader,
    ):
        self.manifest_path = Path(manifest_path)
        self.papers_dir = Path(papers_dir)
        self.results_dir = Path(results_dir) if results_dir else self.manifest_path.parent
        self.top = max(0, int(top or 0))
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
        self.downloader_cls = downloader_cls

    def run(self) -> dict[str, Path]:
        articles = self.load_manifest()
        ranked = self.rank_articles(articles)
        selected = [candidate for candidate in ranked if candidate.eligible][: self.top]
        for candidate in selected:
            candidate.selected_for_download = True

        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.write_ranking(ranked)
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
        return outputs

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
        if self.download_workers <= 1:
            for candidate in selected:
                self.download_one(candidate.article)
            return
        with ThreadPoolExecutor(max_workers=self.download_workers) as executor:
            futures = [executor.submit(self.download_one, candidate.article) for candidate in selected]
            for future in as_completed(futures):
                future.result()

    def download_one(self, article: ArticleRecord) -> ArticleRecord:
        if self.retry_oa_resolution and article.pdf_resolution_status == "provider_no_pdf_url" and not article.pdf_url:
            article.pdf_resolution_status = ""
        downloader = self.downloader_cls(self.papers_dir, timeout=self.timeout)
        return downloader.download(article)

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
            "total_candidates": len(ranked),
            "eligible_candidates": sum(candidate.eligible for candidate in ranked),
            "requested_top_downloads": self.top,
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


def run_from_args(args) -> int:
    service = TopPdfDownloadService(
        manifest_path=Path(args.manifest),
        papers_dir=Path(args.papers_dir),
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        top=getattr(args, "top", 20),
        min_value_score=getattr(args, "min_value_score", None),
        download_workers=getattr(args, "download_workers", 1),
        timeout=getattr(args, "timeout", 15),
        require_doi=getattr(args, "require_doi", False),
        skip_existing=not getattr(args, "include_existing", False),
        retry_oa_resolution=not getattr(args, "no_retry_oa_resolution", False),
        output_manifest_name=getattr(args, "out_manifest_name", "pdf_downloaded_manifest.json"),
    )
    service.run()
    return 0
