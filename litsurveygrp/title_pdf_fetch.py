# -*- coding: utf-8 -*-
"""Fetch PDFs directly from a title or keyword query."""

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import requests

from litsurveygrp.enrichment.metadata_enrichment import (
    clean_abstract,
    clean_doi,
    crossref_authors,
    published_date,
)
from litsurveygrp.manifest_io import ArticleManifestWriter
from litsurveygrp.multi_journal_downloader import OpenAlexSearchProvider
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pdf_download_stage import TopPdfDownloadService
from litsurveygrp.run_monitor import RunMonitor


DEFAULT_SOURCES = ["openalex", "crossref", "europe-pmc"]


@dataclass
class TitlePdfFetchService:
    """Discover papers from a direct title/query and download selected PDFs."""

    out_dir: Path
    title: str = ""
    query: str = ""
    limit: int = 5
    top: int = 1
    sources: list[str] | None = None
    timeout: int = 15
    download_workers: int = 8
    require_doi: bool = False
    include_existing: bool = False
    monitor: RunMonitor | None = None
    session: requests.Session | None = None
    downloader_cls: object | None = None

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.title = (self.title or "").strip()
        self.query = (self.query or "").strip()
        self.limit = max(1, int(self.limit or 1))
        self.top = max(0, int(self.top if self.top is not None else 1))
        self.sources = list(self.sources or DEFAULT_SOURCES)
        self.session = self.session or requests.Session()
        if not self.title and not self.query:
            raise ValueError("fetch-pdf requires --title or --query")

    @property
    def results_dir(self) -> Path:
        return self.out_dir / "results"

    @property
    def papers_dir(self) -> Path:
        return self.out_dir / "papers"

    def run(self) -> dict[str, object]:
        self.start_monitor()
        try:
            discovered = self.discover()
            selected = self.select_for_download(discovered)
            self.results_dir.mkdir(parents=True, exist_ok=True)
            candidate_manifest = ArticleManifestWriter(self.results_dir, "candidate_manifest.json").write(discovered)
            manifest = ArticleManifestWriter(self.results_dir, "article_manifest.json").write(selected)
            outputs: dict[str, object] = {
                "candidate_manifest": candidate_manifest,
                "article_manifest": manifest,
                "discovered_count": len(discovered),
                "selected_count": len(selected),
            }
            if selected and self.top > 0:
                service_kwargs = {}
                if self.downloader_cls is not None:
                    service_kwargs["downloader_cls"] = self.downloader_cls
                download_outputs = TopPdfDownloadService(
                    manifest_path=manifest,
                    papers_dir=self.papers_dir,
                    results_dir=self.results_dir,
                    top=self.top,
                    min_value_score=None,
                    download_workers=self.download_workers,
                    timeout=self.timeout,
                    require_doi=self.require_doi,
                    skip_existing=not self.include_existing,
                    project_name=self.title or self.query or "pdf_fetch",
                    monitor=self.monitor,
                    **service_kwargs,
                ).run()
                outputs["downloaded_manifest"] = download_outputs.get("manifest", "")
                outputs["ranking"] = download_outputs.get("ranking", "")
                outputs["download_report"] = download_outputs.get("download_report", "")
                outputs["download_summary"] = download_outputs.get("summary", "")
            summary = self.write_summary(outputs)
            self.finish_monitor("completed", f"Fetched {len(selected)} candidate papers")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"fetch-pdf failed: {exc}")
            raise

    def discover(self) -> list[ArticleRecord]:
        query = self.title or self.query
        articles: list[ArticleRecord] = []
        if "openalex" in self.sources:
            articles.extend(self.discover_openalex(query))
        if "crossref" in self.sources:
            articles.extend(self.discover_crossref(query))
        if "europe-pmc" in self.sources:
            articles.extend(self.discover_europe_pmc(query))
        articles = dedupe_articles(articles)
        if self.title:
            articles.sort(key=lambda article: (-title_similarity(self.title, article.title), -(article.citation_count or 0), article.title.lower()))
        else:
            articles.sort(key=lambda article: (-(article.citation_count or 0), article.title.lower()))
        return articles[: self.limit]

    def discover_openalex(self, query: str) -> list[ArticleRecord]:
        provider = OpenAlexSearchProvider(
            query=query,
            limit=self.limit,
            timeout=self.timeout,
            session=self.session,
            use_metadata_cache=False,
            monitor=self.monitor,
        )
        return provider.discover()

    def discover_crossref(self, query: str) -> list[ArticleRecord]:
        response = self.session.get(
            "https://api.crossref.org/v1/works",
            params={"query.title": query, "rows": self.limit, "filter": "type:journal-article"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items") or []
        return [crossref_item_to_article(item) for item in items]

    def discover_europe_pmc(self, query: str) -> list[ArticleRecord]:
        if self.title:
            search = f'TITLE:"{self.title}"'
        else:
            search = query
        response = self.session.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": search, "format": "json", "pageSize": self.limit, "resultType": "core"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = (response.json().get("resultList") or {}).get("result") or []
        return [europe_pmc_item_to_article(item) for item in items]

    def select_for_download(self, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        if not self.title:
            return articles
        if self.top <= 0:
            return []
        return articles[: self.top]

    def write_summary(self, outputs: dict[str, object]) -> dict[str, object]:
        summary = {
            "title": self.title,
            "query": self.query,
            "sources": self.sources,
            "limit": self.limit,
            "top": self.top,
            "out_dir": str(self.out_dir),
            "papers_dir": str(self.papers_dir),
            "results_dir": str(self.results_dir),
            "discovered_count": outputs.get("discovered_count", 0),
            "selected_count": outputs.get("selected_count", 0),
            "candidate_manifest": str(outputs.get("candidate_manifest", "")),
            "article_manifest": str(outputs.get("article_manifest", "")),
            "downloaded_manifest": str(outputs.get("downloaded_manifest", "")),
            "ranking": str(outputs.get("ranking", "")),
            "download_report": str(outputs.get("download_report", "")),
            "download_summary": str(outputs.get("download_summary", "")),
            "monitor_status": str(self.monitor.status_path) if self.monitor else "",
        }
        path = self.results_dir / "fetch_pdf_summary.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["fetch_summary"] = str(path)
        return summary

    def start_monitor(self) -> None:
        if self.monitor:
            self.monitor.start(
                "LitSurveyGrp fetch-pdf",
                "Discovering papers from a direct title or keyword query",
                metrics={"title": self.title, "query": self.query, "sources": self.sources},
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def crossref_item_to_article(item: dict) -> ArticleRecord:
    doi = clean_doi(item.get("DOI", ""))
    return ArticleRecord(
        title=first(item.get("title") or [], ""),
        doi=doi,
        journal=first(item.get("container-title") or [], ""),
        article_url=item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
        pdf_url=crossref_pdf_url(item),
        article_type=item.get("type", ""),
        publish_date=published_date(item),
        authors=crossref_authors(item),
        abstract=clean_abstract(item.get("abstract", "")),
        citation_count=item.get("is-referenced-by-count"),
        citation_source="crossref",
        metadata_sources=["crossref"],
        subdomain="PDF Fetch",
        classification_source="direct-query",
    )


def europe_pmc_item_to_article(item: dict) -> ArticleRecord:
    doi = clean_doi(item.get("doi", ""))
    return ArticleRecord(
        title=item.get("title", ""),
        doi=doi,
        journal=item.get("journalTitle", ""),
        article_url=item.get("fullTextUrl", "") or (f"https://doi.org/{doi}" if doi else ""),
        pdf_url=europe_pmc_pdf_url(item),
        article_type=item.get("pubType", ""),
        publish_date=item.get("firstPublicationDate", "") or item.get("pubYear", ""),
        authors=[part.strip() for part in (item.get("authorString", "") or "").split(",") if part.strip()],
        abstract=clean_abstract(item.get("abstractText", "")),
        citation_count=int_or_none(item.get("citedByCount")),
        citation_source="europe-pmc",
        metadata_sources=["europe-pmc"],
        subdomain="PDF Fetch",
        classification_source="direct-query",
    )


def crossref_pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        url = link.get("URL", "")
        content_type = (link.get("content-type") or "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return url
    return ""


def europe_pmc_pdf_url(item: dict) -> str:
    for entry in ((item.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
        url = entry.get("url", "")
        style = (entry.get("documentStyle") or "").lower()
        if "pdf" in style or url.lower().endswith(".pdf"):
            return url
    pmcid = item.get("pmcid") or item.get("pmcId")
    if pmcid:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
    return ""


def dedupe_articles(articles: list[ArticleRecord]) -> list[ArticleRecord]:
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    deduped = []
    for article in articles:
        doi_key = article.doi.casefold()
        title_key = normalize_title(article.title)
        if (doi_key and doi_key in seen_dois) or (title_key and title_key in seen_titles):
            continue
        if doi_key:
            seen_dois.add(doi_key)
        if title_key:
            seen_titles.add(title_key)
        deduped.append(article)
    return deduped


def title_similarity(expected: str, actual: str) -> float:
    return SequenceMatcher(None, normalize_title(expected), normalize_title(actual)).ratio()


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first(values, default=""):
    return values[0] if values else default


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor = RunMonitor(Path(getattr(args, "monitor_dir", "") or Path(args.out) / "results"))
    service = TitlePdfFetchService(
        out_dir=Path(args.out),
        title=getattr(args, "title", ""),
        query=getattr(args, "query", ""),
        limit=getattr(args, "limit", 5),
        top=getattr(args, "top", 1),
        sources=getattr(args, "sources", None),
        timeout=getattr(args, "timeout", 15),
        download_workers=getattr(args, "download_workers", 8),
        require_doi=getattr(args, "require_doi", False),
        include_existing=getattr(args, "include_existing", False),
        monitor=monitor,
    )
    service.run()
    return 0
