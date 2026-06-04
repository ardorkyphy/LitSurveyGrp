# -*- coding: utf-8 -*-
"""
MVP multi-journal downloader.

This module coordinates multiple journal crawlers and delegates PDF handling to
the module-one PdfDownloader implementation.
"""

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from refchaser.filters import ArticleFilter
from refchaser.nature_aging_downloader import NatureJournalCrawler
from refchaser.paper_models import ArticleRecord
from refchaser.pdf_utils import PdfDownloader


@dataclass(frozen=True)
class JournalConfig:
    """Runtime configuration for one supported journal source."""

    name: str
    slug: str = ""
    article_id_prefix: str | None = None
    provider: str = "layered"
    issn: str | None = None
    group: str = "general"
    query: str = ""


SUPPORTED_JOURNALS = {
    "nature-aging": JournalConfig("Nature Aging", "nataging", "s43587-", issn="2662-8465"),
    "nature-medicine": JournalConfig("Nature Medicine", "nm", None, issn="1546-170X"),
    "nature-biotechnology": JournalConfig("Nature Biotechnology", "nbt", None, issn="1546-1696"),
    "nature": JournalConfig("Nature", issn="0028-0836", group="general-top"),
    "science": JournalConfig("Science", issn="0036-8075", group="general-top"),
    "cell": JournalConfig("Cell", issn="0092-8674", group="life-science-top"),
    "nejm": JournalConfig("New England Journal of Medicine", issn="0028-4793", group="medical-top"),
    "lancet": JournalConfig("The Lancet", issn="0140-6736", group="medical-top"),
    "jama": JournalConfig("JAMA", issn="0098-7484", group="medical-top"),
    "tpami": JournalConfig("IEEE Transactions on Pattern Analysis and Machine Intelligence", issn="0162-8828", group="ccf-a-journal"),
    "ijcv": JournalConfig("International Journal of Computer Vision", issn="0920-5691", group="ccf-a-journal"),
    "jacm": JournalConfig("Journal of the ACM", issn="0004-5411", group="ccf-a-journal"),
    "tog": JournalConfig("ACM Transactions on Graphics", issn="0730-0301", group="ccf-a-journal"),
    "tods": JournalConfig("ACM Transactions on Database Systems", issn="0362-5915", group="ccf-a-journal"),
    "tkde": JournalConfig("IEEE Transactions on Knowledge and Data Engineering", issn="1041-4347", group="ccf-a-journal"),
}


class CrossrefJournalProvider:
    """Discover journal articles from Crossref metadata."""

    API_BASE = "https://api.crossref.org/v1"

    def __init__(
        self,
        config: JournalConfig,
        year: int | None = None,
        limit: int | None = None,
        timeout: int = 15,
        session=None,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        if not config.issn:
            raise ValueError("crossref journal config requires issn")
        self.config = config
        self.year = year
        self.from_year = from_year
        self.to_year = to_year
        self.limit = limit
        self.timeout = timeout
        self.session = session or requests.Session()

    def discover(self) -> list[ArticleRecord]:
        """Return ArticleRecord items from the Crossref journal works endpoint."""
        response = self.session.get(
            f"{self.API_BASE}/journals/{self.config.issn}/works",
            params=self.build_params(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        return [self.parse_item(item) for item in items]

    def build_params(self) -> dict:
        """Build Crossref request parameters."""
        filters = ["type:journal-article"]
        if self.year:
            filters.extend([f"from-pub-date:{self.year}-01-01", f"until-pub-date:{self.year}-12-31"])
        else:
            if self.from_year:
                filters.append(f"from-pub-date:{self.from_year}-01-01")
            if self.to_year:
                filters.append(f"until-pub-date:{self.to_year}-12-31")
        return {
            "rows": min(self.limit or 20, 100),
            "sort": "published",
            "order": "desc",
            "filter": ",".join(filters),
        }

    def parse_item(self, item: dict) -> ArticleRecord:
        """Normalize one Crossref item into ArticleRecord."""
        authors = []
        institutions = []
        for author in item.get("author") or []:
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            if name:
                authors.append(name)
            for affiliation in author.get("affiliation") or []:
                value = affiliation.get("name", "").strip()
                if value:
                    institutions.append(value)
        doi = item.get("DOI", "")
        return ArticleRecord(
            title=self._first(item.get("title")),
            doi=doi,
            journal=self._first(item.get("container-title")) or self.config.name,
            article_url=item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
            pdf_url=self._pdf_url(item),
            article_type=item.get("type", ""),
            publish_date=self._published_date(item),
            authors=authors,
            institutions=institutions,
            abstract=self._clean_abstract(item.get("abstract", "")),
        )

    def _pdf_url(self, item: dict) -> str:
        for link in item.get("link") or []:
            url = link.get("URL", "")
            content_type = link.get("content-type", "").lower()
            if "pdf" in content_type or url.lower().endswith(".pdf"):
                return url
        return ""

    def _published_date(self, item: dict) -> str:
        for key in ["published-print", "published-online", "published"]:
            parts = item.get(key, {}).get("date-parts", [])
            if parts and parts[0]:
                return "/".join(str(part) for part in parts[0])
        return ""

    def _clean_abstract(self, value: str) -> str:
        return " ".join(re.sub(r"<[^>]+>", " ", value or "").split())

    def _first(self, value) -> str:
        if isinstance(value, list):
            return str(value[0]).strip() if value else ""
        return str(value or "").strip()


class OpenAlexJournalProvider:
    """Discover journal articles from OpenAlex metadata."""

    API_URL = "https://api.openalex.org/works"

    def __init__(
        self,
        config: JournalConfig,
        year: int | None = None,
        limit: int | None = None,
        timeout: int = 15,
        session=None,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        if not config.issn:
            raise ValueError("openalex journal config requires issn")
        self.config = config
        self.year = year
        self.from_year = from_year
        self.to_year = to_year
        self.limit = limit
        self.timeout = timeout
        self.session = session or requests.Session()

    def discover(self) -> list[ArticleRecord]:
        """Return ArticleRecord items from OpenAlex works."""
        response = self.session.get(self.API_URL, params=self.build_params(), timeout=self.timeout)
        response.raise_for_status()
        items = response.json().get("results", [])
        return [self.parse_item(item) for item in items]

    def build_params(self) -> dict:
        filters = [
            f"primary_location.source.issn:{self.config.issn}",
            "type:article",
        ]
        if self.year:
            filters.extend([f"from_publication_date:{self.year}-01-01", f"to_publication_date:{self.year}-12-31"])
        else:
            if self.from_year:
                filters.append(f"from_publication_date:{self.from_year}-01-01")
            if self.to_year:
                filters.append(f"to_publication_date:{self.to_year}-12-31")
        return {
            "filter": ",".join(filters),
            "sort": "publication_date:desc",
            "per-page": min(self.limit or 50, 200),
        }

    def parse_item(self, item: dict) -> ArticleRecord:
        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        authors = []
        institutions = []
        for authorship in item.get("authorships") or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(author["display_name"])
            for institution in authorship.get("institutions") or []:
                if institution.get("display_name"):
                    institutions.append(institution["display_name"])
        doi = self._clean_doi(item.get("doi", ""))
        pdf_url = self._pdf_url(item)
        return ArticleRecord(
            title=item.get("title", "") or item.get("display_name", ""),
            doi=doi,
            journal=source.get("display_name", "") or self.config.name,
            article_url=item.get("doi", "") or item.get("id", ""),
            pdf_url=pdf_url,
            article_type=item.get("type", ""),
            publish_date=item.get("publication_date", "") or str(item.get("publication_year", "")),
            authors=authors,
            institutions=institutions,
            abstract=self._abstract_text(item.get("abstract_inverted_index") or {}),
            citation_count=item.get("cited_by_count"),
            pdf_resolution_status="provider_pdf_url" if pdf_url else "provider_no_pdf_url",
        )

    def _pdf_url(self, item: dict) -> str:
        primary_location = item.get("primary_location") or {}
        open_access = item.get("open_access") or {}
        for url in [primary_location.get("pdf_url"), open_access.get("oa_url")]:
            if self._looks_like_pdf_url(url or ""):
                return url
        return ""

    def _looks_like_pdf_url(self, url: str) -> bool:
        value = (url or "").lower()
        return value.endswith(".pdf") or "/pdf/" in value or "/pdf" in value or "content/pdf" in value

    def _clean_doi(self, doi: str) -> str:
        return (doi or "").removeprefix("https://doi.org/").strip()

    def _abstract_text(self, inverted_index: dict) -> str:
        words = []
        for word, positions in inverted_index.items():
            for position in positions:
                words.append((position, word))
        return " ".join(word for _, word in sorted(words))


class OpenAlexSearchProvider(OpenAlexJournalProvider):
    """Discover articles from OpenAlex full-work search instead of one journal."""

    def __init__(
        self,
        query: str,
        year: int | None = None,
        limit: int | None = None,
        timeout: int = 15,
        session=None,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        super().__init__(
            JournalConfig(name=f"OpenAlex search: {query}", provider="openalex-search", issn="search"),
            year=year,
            limit=limit,
            timeout=timeout,
            session=session,
            from_year=from_year,
            to_year=to_year,
        )
        self.query = query

    def build_params(self) -> dict:
        params = super().build_params()
        filters = [
            item
            for item in params["filter"].split(",")
            if not item.startswith("primary_location.source.issn:")
        ]
        params["filter"] = ",".join(filters)
        params["search"] = self.query
        return params


class NatureCrawlerJournalProvider:
    """Discover journal articles from Nature-family listing pages."""

    def __init__(
        self,
        config: JournalConfig,
        year: int | None = None,
        limit: int | None = None,
        timeout: int = 15,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        if not config.slug:
            raise ValueError("nature crawler journal config requires slug")
        self.config = config
        self.year = year
        self.limit = limit
        self.timeout = timeout
        self.from_year = from_year
        self.to_year = to_year

    def discover(self) -> list[ArticleRecord]:
        crawler = NatureJournalCrawler(
            journal_name=self.config.name,
            journal_slug=self.config.slug,
            article_id_prefix=self.config.article_id_prefix,
            year=self.year,
            from_year=self.from_year,
            to_year=self.to_year,
        )
        articles = []
        for article_url in crawler.iter_article_urls():
            if self.limit and len(articles) >= self.limit:
                break
            articles.append(crawler.parse_article_detail(crawler.fetch_article_detail(article_url), article_url))
        return articles


class LayeredJournalProvider:
    """Discover articles with OpenAlex first, Crossref second, crawler last."""

    def __init__(
        self,
        config: JournalConfig,
        year: int | None = None,
        limit: int | None = None,
        timeout: int = 15,
        from_year: int | None = None,
        to_year: int | None = None,
        provider_factories: list | None = None,
    ):
        self.config = config
        self.year = year
        self.limit = limit
        self.timeout = timeout
        self.from_year = from_year
        self.to_year = to_year
        self.provider_factories = provider_factories
        self.errors: list[str] = []

    def discover(self) -> list[ArticleRecord]:
        """Return de-duplicated articles from all available provider layers."""
        articles = []
        seen = set()
        for provider in self.build_providers():
            try:
                discovered = provider.discover()
            except Exception as exc:
                self.errors.append(f"{provider.__class__.__name__}:{exc.__class__.__name__}")
                continue
            for article in discovered:
                key = self.article_key(article)
                if key in seen:
                    continue
                seen.add(key)
                articles.append(article)
                if self.limit and len(articles) >= self.limit:
                    return articles
        return articles

    def build_providers(self) -> list:
        if self.provider_factories is not None:
            return [factory() for factory in self.provider_factories]
        providers = []
        if self.config.issn:
            providers.append(OpenAlexJournalProvider(
                self.config,
                year=self.year,
                limit=self.limit,
                timeout=self.timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            ))
            providers.append(CrossrefJournalProvider(
                self.config,
                year=self.year,
                limit=self.limit,
                timeout=self.timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            ))
        if self.config.slug:
            providers.append(NatureCrawlerJournalProvider(
                self.config,
                year=self.year,
                limit=self.limit,
                timeout=self.timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            ))
        return providers

    def article_key(self, article: ArticleRecord) -> str:
        if article.doi:
            return "doi:" + article.doi.casefold().strip()
        if article.article_url:
            return "url:" + article.article_url.casefold().strip()
        return "title:" + article.title.casefold().strip()


class MultiJournalDownloadService:
    """Download complete PDFs across multiple journals using shared PDF logic."""

    def __init__(
        self,
        output_dir: Path,
        journals: list[JournalConfig],
        year: int | None = None,
        limit: int | None = None,
        per_journal_limit: int | None = None,
        dry_run: bool = False,
        manifest_name: str = "multi_journal_manifest.json",
        report_name: str = "multi_journal_download_report.csv",
        results_dir: Path | None = None,
        download_timeout: int = 15,
        pdf_only_candidates: bool = False,
        article_filter: ArticleFilter | None = None,
        prefilter_enricher=None,
        from_year: int | None = None,
        to_year: int | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.results_dir = Path(results_dir) if results_dir else self.output_dir
        self.journals = journals
        self.year = year
        self.from_year = from_year
        self.to_year = to_year
        self.limit = limit
        self.per_journal_limit = per_journal_limit
        self.dry_run = dry_run
        self.manifest_name = manifest_name
        self.report_name = report_name
        self.download_timeout = download_timeout
        self.pdf_only_candidates = pdf_only_candidates
        self.article_filter = article_filter
        self.prefilter_enricher = prefilter_enricher
        self.source_errors: list[str] = []
        self.downloader = PdfDownloader(self.output_dir, timeout=download_timeout)

    def run(self) -> list[ArticleRecord]:
        """Discover and download articles across all configured journals."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        articles = []
        complete_count = 0
        for article in self.iter_articles():
            article = self.prepare_article_for_filtering(article)
            if self.article_filter and not self.article_filter.matches(article):
                continue
            if self.pdf_only_candidates and not article.pdf_url:
                article.download_status = "skipped"
                article.pdf_status = "missing_pdf_url"
                article.error = "provider did not supply a direct PDF URL"
                articles.append(article)
                continue
            if self.dry_run:
                article.download_status = "dry_run"
                article.pdf_status = "unchecked"
            else:
                article = self.downloader.download(article)
            articles.append(article)
            if article.pdf_status == "complete" and article.local_pdf_path:
                complete_count += 1
            if self.limit and complete_count >= self.limit:
                break
        self.write_manifest(articles)
        self.write_report(articles)
        return articles

    def prepare_article_for_filtering(self, article: ArticleRecord) -> ArticleRecord:
        """Enrich fields needed by filters before deciding whether to download."""
        if (
            self.article_filter
            and self.article_filter.needs_citation_count()
            and article.citation_count is None
            and self.prefilter_enricher is not None
        ):
            return self.prefilter_enricher.enrich_article(article)
        return article

    def iter_articles(self):
        """Yield discovered articles from each configured journal."""
        for journal in self.journals:
            source = self.build_source(journal)
            try:
                articles = source.discover()
            except Exception as exc:
                self.source_errors.append(f"{journal.name}:{source.__class__.__name__}:{exc.__class__.__name__}")
                continue
            if getattr(source, "errors", None):
                self.source_errors.extend(f"{journal.name}:{error}" for error in source.errors)
            for article in articles:
                yield article

    def build_source(self, journal: JournalConfig):
        """Create a source provider for one journal config."""
        if journal.provider == "crossref":
            return CrossrefJournalProvider(
                journal,
                year=self.year,
                limit=self.per_journal_limit,
                timeout=self.download_timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            )
        if journal.provider == "openalex":
            return OpenAlexJournalProvider(
                journal,
                year=self.year,
                limit=self.per_journal_limit,
                timeout=self.download_timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            )
        if journal.provider == "openalex-search":
            return OpenAlexSearchProvider(
                journal.query or journal.name,
                year=self.year,
                limit=self.per_journal_limit,
                timeout=self.download_timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            )
        if journal.provider == "nature":
            return NatureCrawlerJournalProvider(
                journal,
                year=self.year,
                limit=self.per_journal_limit,
                timeout=self.download_timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            )
        if journal.provider == "layered":
            return LayeredJournalProvider(
                journal,
                year=self.year,
                limit=self.per_journal_limit,
                timeout=self.download_timeout,
                from_year=self.from_year,
                to_year=self.to_year,
            )
        if journal.provider != "nature":
            raise ValueError(f"unsupported journal provider: {journal.provider}")

    def write_manifest(self, articles: list[ArticleRecord]) -> Path:
        """Write a JSON manifest."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / self.manifest_name
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return path

    def write_report(self, articles: list[ArticleRecord]) -> Path:
        """Write a CSV download report."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / self.report_name
        fields = [
            "journal",
            "title",
            "doi",
            "pdf_url",
            "local_pdf_path",
            "download_status",
            "pdf_status",
            "error",
        ]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for article in articles:
                row = article.to_manifest_dict()
                writer.writerow({field: row.get(field, "") for field in fields})
        return path


def parse_journal_specs(values: list[str]) -> list[JournalConfig]:
    """Parse CLI journal specs.

    Supported forms:
    - built-in key: nature-aging
    - custom layered journal by ISSN: "layered:Journal Name=ISSN"
    - custom Crossref journal: "crossref:Journal Name=ISSN"
    - custom OpenAlex journal: "openalex:Journal Name=ISSN"
    - custom Nature journal: "Journal Name=slug"
    - custom Nature journal with prefix: "Journal Name=slug:prefix"
    """
    configs = []
    for value in values:
        spec = value.strip()
        if not spec:
            continue
        if spec in SUPPORTED_JOURNALS:
            configs.append(SUPPORTED_JOURNALS[spec])
            continue
        provider, prefixed_spec = _split_provider_prefix(spec)
        if provider in {"crossref", "openalex", "layered"}:
            name, issn = _split_name_value(prefixed_spec)
            configs.append(JournalConfig(name=name, provider=provider, issn=issn, group="custom"))
            continue
        if "=" not in spec:
            raise ValueError(f"unknown journal spec: {spec}")
        name, raw_slug = spec.split("=", 1)
        slug, _, prefix = raw_slug.partition(":")
        configs.append(JournalConfig(
            name=name.strip(),
            slug=slug.strip(),
            article_id_prefix=prefix.strip() or None,
            provider="nature",
        ))
    if not configs:
        raise ValueError("at least one journal must be provided")
    return configs


def _split_name_value(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise ValueError(f"invalid journal spec: {spec}")
    name, value = spec.split("=", 1)
    name = name.strip()
    value = value.strip()
    if not name or not value:
        raise ValueError(f"invalid journal spec: {spec}")
    return name, value


def _split_provider_prefix(spec: str) -> tuple[str, str]:
    provider, separator, remainder = spec.partition(":")
    if separator and provider in {"crossref", "openalex", "layered"}:
        return provider, remainder
    return "", spec


def list_supported_journals(group: str | None = None) -> list[tuple[str, JournalConfig]]:
    """Return supported journal catalog entries."""
    items = sorted(SUPPORTED_JOURNALS.items())
    if group:
        items = [(key, config) for key, config in items if config.group == group]
    return items


def run_list_from_args(args) -> int:
    """CLI adapter for python -m refchaser list-journals."""
    for key, config in list_supported_journals(getattr(args, "group", None)):
        locator = config.issn or config.slug
        print(f"{key}\t{config.name}\t{config.provider}\t{locator}\t{config.group}")
    return 0


def run_from_args(args) -> int:
    """CLI adapter for python -m refchaser download-journals."""
    service = MultiJournalDownloadService(
        output_dir=Path(args.to),
        journals=parse_journal_specs(args.journal),
        year=args.year,
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        limit=args.limit,
        per_journal_limit=args.per_journal_limit,
        dry_run=args.dry_run,
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        download_timeout=getattr(args, "download_timeout", 15),
        pdf_only_candidates=getattr(args, "pdf_only_candidates", False),
        article_filter=build_article_filter_from_args(args),
        prefilter_enricher=build_prefilter_enricher_from_args(args),
    )
    service.run()
    return 0


def run_nature_aging_from_args(args) -> int:
    """Compatibility adapter for python -m refchaser download-nature-aging."""
    service = MultiJournalDownloadService(
        output_dir=Path(args.to),
        journals=[SUPPORTED_JOURNALS["nature-aging"]],
        year=args.year,
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        limit=args.limit,
        per_journal_limit=None,
        dry_run=args.dry_run,
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        download_timeout=getattr(args, "download_timeout", 15),
        pdf_only_candidates=getattr(args, "pdf_only_candidates", False),
        article_filter=build_article_filter_from_args(args),
        prefilter_enricher=build_prefilter_enricher_from_args(args),
        manifest_name="article_manifest.json",
        report_name="download_report.csv",
    )
    service.run()
    return 0


def build_article_filter_from_args(args) -> ArticleFilter | None:
    article_filter = ArticleFilter(
        keywords=list(getattr(args, "keyword", None) or []),
        article_types=list(getattr(args, "article_type", None) or []),
        min_citations=getattr(args, "min_citations", None),
        year=getattr(args, "year", None),
        from_year=getattr(args, "from_year", None),
        to_year=getattr(args, "to_year", None),
        authors=list(getattr(args, "author", None) or []),
        institutions=list(getattr(args, "institution", None) or []),
    )
    return article_filter if article_filter.has_criteria() else None


def build_prefilter_enricher_from_args(args):
    if getattr(args, "min_citations", None) is None:
        return None
    from refchaser.enrichment.metadata_enrichment import MetadataEnrichmentService

    return MetadataEnrichmentService(
        "article_prefilter.json",
        sources=list(getattr(args, "filter_sources", None) or ["openalex", "crossref"]),
        timeout=getattr(args, "metadata_timeout", getattr(args, "download_timeout", 15)),
        request_interval=getattr(args, "request_interval", 1.0),
    )
