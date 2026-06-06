# -*- coding: utf-8 -*-
"""
Metadata enrichment from open scholarly metadata APIs.

The service is intentionally conservative: resolvers normalize external
responses into ArticleRecord fields, while merge logic fills missing metadata
and records where citation counts and abstracts came from.
"""

import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests

from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.run_monitor import RunMonitor
from litsurveygrp.multi_journal_downloader import openalex_authoritative_topics


DEFAULT_SOURCES = ["openalex", "semantic-scholar", "europe-pmc", "crossref"]
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.0
DEFAULT_FAILURE_BREAKER_THRESHOLD = 10
CITATION_POLICY_MAX_AVAILABLE = "max_available"


class OpenAlexMetadataResolver:
    """Resolve DOI/title metadata from OpenAlex."""

    name = "openalex"
    API_BASE = "https://api.openalex.org/works"

    def __init__(self, session=None, timeout: int = 15, api_key: str | None = None):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY", "")

    def can_help(self, article: ArticleRecord) -> bool:
        missing = missing_metadata_fields(article)
        supported = {
            "doi", "journal", "article_type", "abstract", "authors",
            "institutions", "publish_date", "citation_count", "authoritative_topics",
        }
        return bool(article.doi or article.title) and bool(missing & supported)

    def resolve(self, article: ArticleRecord) -> dict:
        data = self._fetch(article)
        if not data:
            return {}
        return {
            "title": data.get("title") or data.get("display_name", ""),
            "doi": clean_doi(data.get("doi", "")),
            "journal": ((data.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
            "publish_date": data.get("publication_date", "") or str(data.get("publication_year", "") or ""),
            "article_type": data.get("type", ""),
            "authors": self._authors(data),
            "institutions": self._institutions(data),
            "abstract": openalex_abstract(data.get("abstract_inverted_index") or {}),
            "citation_count": data.get("cited_by_count"),
            "authoritative_topics": openalex_authoritative_topics(data),
        }

    def _fetch(self, article: ArticleRecord) -> dict:
        if article.doi:
            response = self.session.get(
                f"{self.API_BASE}/doi:{quote(clean_doi(article.doi), safe='')}",
                params=self.auth_params(),
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        if not article.title:
            return {}
        response = self.session.get(
            self.API_BASE,
            params=self.auth_params({"search": article.title, "per-page": 1}),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return first((response.json().get("results") or []), {})

    def auth_params(self, params: dict | None = None) -> dict:
        params = dict(params or {})
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _authors(self, data: dict) -> list[str]:
        return dedupe([
            (authorship.get("author") or {}).get("display_name", "")
            for authorship in data.get("authorships") or []
        ])

    def _institutions(self, data: dict) -> list[str]:
        values = []
        for authorship in data.get("authorships") or []:
            for institution in authorship.get("institutions") or []:
                values.append(institution.get("display_name", ""))
        return dedupe(values)


class SemanticScholarMetadataResolver:
    """Resolve DOI/title metadata from Semantic Scholar Graph API."""

    name = "semantic-scholar"
    API_BASE = "https://api.semanticscholar.org/graph/v1"
    FIELDS = "title,abstract,year,authors,citationCount,venue,publicationTypes,publicationDate,externalIds"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        missing = missing_metadata_fields(article)
        supported = {"doi", "journal", "article_type", "abstract", "authors", "publish_date", "citation_count"}
        return bool(article.doi or article.title) and bool(missing & supported)

    def resolve(self, article: ArticleRecord) -> dict:
        data = self._fetch(article)
        if not data:
            return {}
        external_ids = data.get("externalIds") or {}
        publication_types = data.get("publicationTypes") or []
        return {
            "title": data.get("title", ""),
            "doi": external_ids.get("DOI", ""),
            "journal": data.get("venue", ""),
            "publish_date": data.get("publicationDate", "") or str(data.get("year", "") or ""),
            "article_type": first(publication_types, ""),
            "authors": [author.get("name", "") for author in data.get("authors") or []],
            "abstract": data.get("abstract", ""),
            "citation_count": data.get("citationCount"),
        }

    def _fetch(self, article: ArticleRecord) -> dict:
        if article.doi:
            response = self.session.get(
                f"{self.API_BASE}/paper/DOI:{quote(clean_doi(article.doi), safe='')}",
                params={"fields": self.FIELDS},
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        if not article.title:
            return {}
        response = self.session.get(
            f"{self.API_BASE}/paper/search",
            params={"query": article.title, "limit": 1, "fields": self.FIELDS},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return first((response.json().get("data") or []), {})


class EuropePmcMetadataResolver:
    """Resolve biomedical metadata from Europe PMC."""

    name = "europe-pmc"
    API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        missing = missing_metadata_fields(article)
        supported = {"doi", "journal", "article_type", "abstract", "authors", "publish_date", "citation_count"}
        if not bool(article.doi or article.title) or not missing & supported:
            return False
        return looks_biomedical(article)

    def resolve(self, article: ArticleRecord) -> dict:
        query = f'DOI:"{clean_doi(article.doi)}"' if article.doi else f'TITLE:"{article.title}"'
        if not article.doi and not article.title:
            return {}
        response = self.session.get(
            self.API_URL,
            params={"query": query, "format": "json", "pageSize": 1, "resultType": "core"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = first(((response.json().get("resultList") or {}).get("result") or []), {})
        if not data:
            return {}
        return {
            "title": data.get("title", ""),
            "doi": data.get("doi", ""),
            "journal": data.get("journalTitle", ""),
            "publish_date": data.get("firstPublicationDate", "") or data.get("pubYear", ""),
            "article_type": data.get("pubType", ""),
            "authors": split_authors(data.get("authorString", "")),
            "abstract": data.get("abstractText", ""),
            "citation_count": int_or_none(data.get("citedByCount")),
        }


class CrossrefMetadataResolver:
    """Resolve DOI/title metadata from Crossref."""

    name = "crossref"
    API_BASE = "https://api.crossref.org/v1/works"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        missing = missing_metadata_fields(article)
        supported = {
            "doi", "journal", "article_type", "publish_date",
            "authors", "institutions", "abstract", "citation_count",
        }
        return bool(article.doi or article.title) and bool(missing & supported)

    def resolve(self, article: ArticleRecord) -> dict:
        data = self._fetch(article)
        if not data:
            return {}
        return {
            "title": first(data.get("title") or [], ""),
            "doi": data.get("DOI", ""),
            "journal": first(data.get("container-title") or [], ""),
            "publish_date": published_date(data),
            "article_type": data.get("type", ""),
            "authors": crossref_authors(data),
            "institutions": crossref_institutions(data),
            "abstract": clean_abstract(data.get("abstract", "")),
            "citation_count": data.get("is-referenced-by-count"),
        }

    def _fetch(self, article: ArticleRecord) -> dict:
        if article.doi:
            response = self.session.get(
                f"{self.API_BASE}/{quote(clean_doi(article.doi), safe='')}",
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json().get("message", {})
        if not article.title:
            return {}
        response = self.session.get(
            self.API_BASE,
            params={"query.title": article.title, "rows": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return first((response.json().get("message", {}).get("items") or []), {})


class MetadataEnrichmentService:
    """Load a manifest, enrich records, and write enriched_manifest.json."""

    def __init__(
        self,
        manifest_path: Path,
        sources: list[str] | None = None,
        output_path: Path | None = None,
        timeout: int = 15,
        request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        session=None,
        resolvers: list | None = None,
        sleep_func=None,
        monotonic_func=None,
        monitor: RunMonitor | None = None,
        workers: int = 1,
        failure_breaker_threshold: int = DEFAULT_FAILURE_BREAKER_THRESHOLD,
    ):
        self.manifest_path = Path(manifest_path)
        load_local_env(self.manifest_path.parent)
        self.output_path = Path(output_path) if output_path else self.manifest_path.parent / "enriched_manifest.json"
        self.sources = sources or list(DEFAULT_SOURCES)
        self.timeout = timeout
        self.request_interval = max(0.0, float(request_interval))
        self.session = session
        self.resolvers = resolvers or self.build_resolvers()
        self.sleep_func = sleep_func or time.sleep
        self.monotonic_func = monotonic_func or time.monotonic
        self._last_request_at: float | None = None
        self._last_request_by_source: dict[str, float] = {}
        self._source_locks: dict[str, threading.Lock] = {}
        self._source_locks_lock = threading.Lock()
        self._breaker_lock = threading.Lock()
        self.workers = max(1, int(workers or 1))
        self.failure_breaker_threshold = max(0, int(failure_breaker_threshold or 0))
        self._consecutive_failures: dict[str, int] = {}
        self._disabled_sources: set[str] = set()
        self.monitor = monitor or RunMonitor(self.output_path.parent)

    def build_resolvers(self) -> list:
        registry = {
            "openalex": OpenAlexMetadataResolver,
            "semantic-scholar": SemanticScholarMetadataResolver,
            "europe-pmc": EuropePmcMetadataResolver,
            "crossref": CrossrefMetadataResolver,
        }
        resolvers = []
        for source in self.sources:
            if source not in registry:
                raise ValueError(f"unsupported metadata source: {source}")
            resolvers.append(registry[source](session=self.session, timeout=self.timeout))
        return resolvers

    def run(self) -> list[ArticleRecord]:
        source_articles = self.load_manifest()
        self.monitor.start(
            "Metadata enrichment",
            "Enriching paper metadata from open scholarly APIs",
            metrics={
                "sources": ", ".join(self.sources),
                "request_interval": self.request_interval,
                "total_records": len(source_articles),
            },
        )
        articles = self.enrich_articles(source_articles)
        self.write_manifest(articles)
        self.monitor.finish("completed", f"Metadata enrichment finished with {len(articles)} records")
        return articles

    def enrich_articles(self, source_articles: list[ArticleRecord]) -> list[ArticleRecord]:
        if self.workers <= 1 or len(source_articles) <= 1:
            articles = []
            for index, article in enumerate(source_articles, start=1):
                self.monitor.update(
                    stage="enrich",
                    message=f"Enriching record {index} of {len(source_articles)}",
                    processed=index - 1,
                    total=len(source_articles),
                    current_item=article.title or article.doi,
                )
                articles.append(self.enrich_article(article))
                self.monitor.update(
                    stage="enrich",
                    message=f"Enriched record {index} of {len(source_articles)}",
                    processed=index,
                    total=len(source_articles),
                    current_item=article.title or article.doi,
                    metrics=self.article_metrics(article),
                )
            return articles

        articles: list[ArticleRecord | None] = [None] * len(source_articles)
        completed = 0
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self.enrich_article, article): (index, article)
                for index, article in enumerate(source_articles)
            }
            for future in as_completed(futures):
                index, original = futures[future]
                article = future.result()
                articles[index] = article
                completed += 1
                self.monitor.update(
                    stage="enrich",
                    message=f"Enriched record {completed} of {len(source_articles)}",
                    processed=completed,
                    total=len(source_articles),
                    current_item=article.title or original.title or article.doi or original.doi,
                    metrics=self.article_metrics(article),
                )
        return [article for article in articles if article is not None]

    def article_metrics(self, article: ArticleRecord) -> dict:
        return {
            "last_enrichment_status": article.enrichment_status,
            "last_metadata_sources": ", ".join(article.metadata_sources),
            "last_citation_source": article.citation_source,
            "disabled_metadata_sources": ", ".join(sorted(self._disabled_sources)),
        }

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def write_manifest(self, articles: list[ArticleRecord]) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return self.output_path

    def enrich_article(self, article: ArticleRecord) -> ArticleRecord:
        if self.has_sufficient_metadata(article):
            article.enrichment_status = "sufficient_from_discovery"
            return article
        found_sources = []
        errors = []
        for resolver in self.resolvers:
            if self.is_source_disabled(resolver.name):
                continue
            if not self.resolver_can_help(resolver, article):
                continue
            self.monitor.update(
                stage="enrich",
                message=f"Calling {resolver.name}",
                current_item=article.title or article.doi,
                metrics={"current_metadata_source": resolver.name},
            )
            try:
                self.throttle(resolver.name)
                metadata = self._clean_metadata(resolver.resolve(article))
            except Exception as exc:
                errors.append(f"{resolver.name}:{exc.__class__.__name__}")
                self.record_source_failure(resolver.name, exc)
                self.monitor.add_event("metadata_error", f"{resolver.name}: {exc.__class__.__name__}")
                self.monitor.write()
                continue
            if not metadata:
                continue
            self.merge_metadata(article, metadata, resolver.name)
            found_sources.append(resolver.name)
            self.record_source_success(resolver.name)
        article.metadata_sources = dedupe(list(article.metadata_sources) + found_sources)
        if found_sources:
            article.enrichment_status = "enriched"
        elif errors:
            article.enrichment_status = "error:" + ",".join(errors[:4])
        else:
            article.enrichment_status = "not_found"
        return article

    def resolver_can_help(self, resolver, article: ArticleRecord) -> bool:
        can_help = getattr(resolver, "can_help", None)
        if can_help is None:
            return True
        return bool(can_help(article))

    def throttle(self, source: str = "") -> None:
        """Respect a minimum interval between external metadata API calls."""
        key = source or "__global__"
        with self._source_lock(key):
            if self.request_interval <= 0:
                self._last_request_at = self.monotonic_func()
                if source:
                    self._last_request_by_source[source] = self._last_request_at
                return
            now = self.monotonic_func()
            last_request_at = self._last_request_by_source.get(key)
            if last_request_at is not None:
                elapsed = now - last_request_at
                wait_seconds = self.request_interval - elapsed
                if wait_seconds > 0:
                    self.sleep_func(wait_seconds)
                    now = self.monotonic_func()
            self._last_request_at = now
            self._last_request_by_source[key] = now

    def _source_lock(self, source: str) -> threading.Lock:
        with self._source_locks_lock:
            if source not in self._source_locks:
                self._source_locks[source] = threading.Lock()
            return self._source_locks[source]

    def has_sufficient_metadata(self, article: ArticleRecord) -> bool:
        """Return whether discovery metadata is already strong enough to skip enrichment calls."""
        return all([
            bool(article.title),
            bool(article.doi),
            bool(article.abstract),
            bool(article.authors),
            bool(article.publish_date),
            article.citation_count is not None,
            bool(article.authoritative_topics),
        ])

    def is_source_disabled(self, source: str) -> bool:
        with self._breaker_lock:
            return source in self._disabled_sources

    def record_source_success(self, source: str) -> None:
        with self._breaker_lock:
            self._consecutive_failures[source] = 0

    def record_source_failure(self, source: str, exc: Exception) -> None:
        if self.failure_breaker_threshold <= 0:
            return
        disabled = False
        count = 0
        with self._breaker_lock:
            count = self._consecutive_failures.get(source, 0) + 1
            self._consecutive_failures[source] = count
            if count >= self.failure_breaker_threshold and source not in self._disabled_sources:
                self._disabled_sources.add(source)
                disabled = True
        if disabled:
            self.monitor.add_event(
                "metadata_source_disabled",
                f"{source} disabled after {count} consecutive {exc.__class__.__name__} errors",
            )
            self.monitor.write()

    def merge_metadata(self, article: ArticleRecord, metadata: dict, source: str) -> bool:
        changed = False
        for field_name in ["title", "doi", "journal", "article_type", "publish_date"]:
            value = metadata.get(field_name)
            if value and not getattr(article, field_name):
                setattr(article, field_name, value)
                changed = True
        for field_name in ["authors", "institutions"]:
            values = dedupe(metadata.get(field_name) or [])
            if values and not getattr(article, field_name):
                setattr(article, field_name, values)
                changed = True
        if metadata.get("abstract") and not article.abstract:
            article.abstract = metadata["abstract"]
            article.abstract_source = source
            changed = True
        if metadata.get("citation_count") is not None:
            changed = self.merge_citation_count(article, int(metadata["citation_count"]), source) or changed
        if metadata.get("authoritative_topics"):
            merged = merge_topic_lists(article.authoritative_topics, metadata["authoritative_topics"])
            if merged != article.authoritative_topics:
                article.authoritative_topics = merged
                changed = True
        return changed

    def merge_citation_count(self, article: ArticleRecord, citation_count: int, source: str) -> bool:
        previous = dict(article.citation_counts)
        article.citation_counts[source] = citation_count
        best_source, best_count = self.best_citation_count(article.citation_counts)
        old_count = article.citation_count
        old_source = article.citation_source
        old_policy = article.citation_policy
        article.citation_count = best_count
        article.citation_source = best_source
        article.citation_policy = CITATION_POLICY_MAX_AVAILABLE
        return (
            previous != article.citation_counts
            or old_count != article.citation_count
            or old_source != article.citation_source
            or old_policy != article.citation_policy
        )

    def best_citation_count(self, citation_counts: dict[str, int]) -> tuple[str, int | None]:
        if not citation_counts:
            return "", None
        best_source, best_count = max(
            citation_counts.items(),
            key=lambda item: (int(item[1]), self.citation_source_priority(item[0])),
        )
        return best_source, int(best_count)

    def citation_source_priority(self, source: str) -> int:
        priority = {
            "semantic-scholar": 4,
            "openalex": 3,
            "europe-pmc": 2,
            "crossref": 1,
        }
        return priority.get(source, 0)

    def _clean_metadata(self, metadata: dict | None) -> dict:
        metadata = metadata or {}
        cleaned = dict(metadata)
        if cleaned.get("doi"):
            cleaned["doi"] = clean_doi(cleaned["doi"])
        if cleaned.get("abstract"):
            cleaned["abstract"] = clean_abstract(cleaned["abstract"])
        if cleaned.get("citation_count") is not None:
            cleaned["citation_count"] = int_or_none(cleaned["citation_count"])
        return {key: value for key, value in cleaned.items() if value not in ("", [], None)}


def openalex_abstract(index: dict) -> str:
    words = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def missing_metadata_fields(article: ArticleRecord) -> set[str]:
    missing = set()
    if not article.doi:
        missing.add("doi")
    if not article.journal:
        missing.add("journal")
    if not article.article_type:
        missing.add("article_type")
    if not article.publish_date:
        missing.add("publish_date")
    if not article.authors:
        missing.add("authors")
    if not article.institutions:
        missing.add("institutions")
    if not article.abstract:
        missing.add("abstract")
    if article.citation_count is None:
        missing.add("citation_count")
    if not article.authoritative_topics:
        missing.add("authoritative_topics")
    return missing


def looks_biomedical(article: ArticleRecord) -> bool:
    text = " ".join([
        article.title or "",
        article.abstract or "",
        article.journal or "",
        article.article_type or "",
        " ".join(topic.get("label", "") for topic in article.authoritative_topics or []),
    ]).lower()
    terms = [
        "medicine", "medical", "clinical", "biomedical", "biology", "neuroscience",
        "brain", "neuro", "disease", "patient", "therapy", "diagnosis", "health",
    ]
    return any(term in text for term in terms)


def merge_topic_lists(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("source") or "").casefold(),
            str(item.get("taxonomy") or "").casefold(),
            str(item.get("label") or "").casefold(),
        )
        if not key[2] or key in seen:
            continue
        seen.add(key)
        merged.append(dict(item))
    return merged


def published_date(item: dict) -> str:
    for key in ["published-print", "published-online", "published"]:
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            return "/".join(str(part) for part in parts[0])
    return ""


def crossref_authors(item: dict) -> list[str]:
    values = []
    for author in item.get("author") or []:
        values.append(" ".join(part for part in [author.get("given", ""), author.get("family", "")] if part))
    return dedupe(values)


def crossref_institutions(item: dict) -> list[str]:
    values = []
    for author in item.get("author") or []:
        for affiliation in author.get("affiliation") or []:
            values.append(affiliation.get("name", ""))
    return dedupe(values)


def clean_abstract(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value or "").split())


def clean_doi(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    return value.strip()


def split_authors(value: str) -> list[str]:
    return dedupe([part.strip() for part in re.split(r"\s*;\s*", value or "") if part.strip()])


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def first(values, default=None):
    return values[0] if values else default


def int_or_none(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_local_env(start_dir: Path | None = None) -> None:
    """Load simple KEY=VALUE lines from a local .env file without overwriting env vars."""
    search_dirs = []
    if start_dir:
        search_dirs.extend([Path(start_dir), *Path(start_dir).parents])
    search_dirs.extend([Path.cwd(), *Path.cwd().parents])
    seen = set()
    for directory in search_dirs:
        env_path = directory / ".env"
        if env_path in seen:
            continue
        seen.add(env_path)
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp enrich-metadata."""
    service = MetadataEnrichmentService(
        Path(args.manifest),
        sources=getattr(args, "sources", None),
        output_path=Path(args.out) if getattr(args, "out", None) else None,
        timeout=getattr(args, "timeout", 15),
        request_interval=getattr(args, "request_interval", DEFAULT_REQUEST_INTERVAL_SECONDS),
        workers=getattr(args, "workers", 1),
    )
    service.run()
    return 0

