# -*- coding: utf-8 -*-
"""Reference-paper analysis, ranking, and selective download."""

import csv
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from litsurveygrp.enrichment.metadata_enrichment import (
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    MetadataEnrichmentService,
)
from litsurveygrp.journal_tiers import DEFAULT_JOURNAL_TIER_MAP, JournalTierScorer
from litsurveygrp.paper_classifier import SentenceTransformerEmbedder
from litsurveygrp.paper_models import ArticleRecord, ReferenceRecord
from litsurveygrp.pdf_utils import PdfDownloader
from litsurveygrp.reference_extractor import PdfReferenceExtractor
from litsurveygrp.analysis_paths import article_subdomain, major_domain_name, report_data_dir


DEFAULT_REFERENCE_SOURCES = ["openalex", "europe-pmc", "crossref"]


class ReferenceMetadataEnricher:
    """Enrich ReferenceRecord instances through existing ArticleRecord resolvers."""

    def __init__(
        self,
        work_dir: Path,
        sources: list[str] | None = None,
        timeout: int = 15,
        request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    ):
        self.service = MetadataEnrichmentService(
            Path(work_dir) / "reference_metadata_prefetch.json",
            sources=sources or list(DEFAULT_REFERENCE_SOURCES),
            timeout=timeout,
            request_interval=request_interval,
        )

    def enrich_reference(self, reference: ReferenceRecord) -> ReferenceRecord:
        article = ArticleRecord(
            title=reference.title,
            doi=reference.doi,
            journal=reference.journal,
            publish_date=reference.publish_date,
            authors=list(reference.authors),
            abstract=reference.abstract,
            citation_count=reference.citation_count,
            citation_source=reference.citation_source,
            citation_counts=dict(reference.citation_counts),
            metadata_sources=list(reference.metadata_sources),
        )
        article = self.service.enrich_article(article)
        reference.title = article.title or reference.title
        reference.doi = article.doi or reference.doi
        reference.journal = article.journal or reference.journal
        reference.publish_date = article.publish_date or reference.publish_date
        reference.authors = article.authors or reference.authors
        reference.abstract = article.abstract or reference.abstract
        reference.citation_count = article.citation_count
        reference.citation_source = article.citation_source
        reference.citation_counts = dict(article.citation_counts)
        reference.metadata_sources = list(article.metadata_sources)
        return reference


class ReferenceRelevanceScorer:
    """Score reference relevance against a survey profile."""

    def __init__(
        self,
        threshold: float = 0.30,
        query: str = "",
        embedder=None,
    ):
        self.threshold = threshold
        self.query = query
        self.embedder = embedder

    def build_profile_text(self, articles: list[ArticleRecord]) -> str:
        if self.query:
            return self.query
        parts = []
        for article in articles:
            parts.extend([
                article.title,
                article.abstract,
                article.subdomain,
                article.problem_statement,
                article.solution_summary or "",
            ])
        return " ".join(part for part in parts if part)[:20000]

    def score(self, reference: ReferenceRecord, profile_text: str) -> ReferenceRecord:
        reference_text = " ".join([
            reference.title,
            reference.abstract,
            reference.journal,
            " ".join(reference.authors),
        ])
        if self.embedder and self.embedder.can_embed() and profile_text.strip() and reference_text.strip():
            score = cosine_pair(self.embedder.embed([profile_text, reference_text]))
            reference.relevance_score = round(score, 3)
            reference.relevance_reason = "SPECTER cosine similarity"
            return reference
        score, reason = token_relevance(profile_text, reference_text)
        reference.relevance_score = round(score, 3)
        reference.relevance_reason = reason
        return reference


class ReferenceValueScorer:
    """Combine relevance, citations, journal tier, recency, and metadata coverage."""

    def __init__(self, current_year: int | None = None, journal_scorer: JournalTierScorer | None = None):
        self.current_year = current_year or datetime.now().year
        self.journal_scorer = journal_scorer or JournalTierScorer()

    def score_batch(self, references: list[ReferenceRecord]) -> list[ReferenceRecord]:
        max_citations = max([int(ref.citation_count or 0) for ref in references] or [0])
        for reference in references:
            self.score(reference, max_citations=max_citations)
        return references

    def score(self, reference: ReferenceRecord, max_citations: int = 0) -> ReferenceRecord:
        tier, tier_score = self.journal_scorer.score(reference.journal)
        reference.journal_tier = tier
        reference.journal_tier_score = round(tier_score, 3)
        citation_score = self._citation_score(reference.citation_count or 0, max_citations)
        source_count_score = min(1.0, reference.source_article_count / 5)
        recency_score = self._recency_score(reference.publish_date)
        metadata_score = self._metadata_score(reference)
        value = (
            0.35 * reference.relevance_score
            + 0.20 * citation_score
            + 0.15 * tier_score
            + 0.10 * source_count_score
            + 0.10 * recency_score
            + 0.10 * metadata_score
        )
        reference.value_score = round(min(1.0, value), 3)
        reference.value_reason = (
            f"relevance={reference.relevance_score:.3f}; "
            f"citations={citation_score:.3f}; journal={tier}:{tier_score:.3f}; "
            f"co-cited={source_count_score:.3f}; recency={recency_score:.3f}; metadata={metadata_score:.3f}"
        )
        return reference

    def _citation_score(self, citations: int, max_citations: int) -> float:
        if citations <= 0 or max_citations <= 0:
            return 0.0
        return min(1.0, math.log1p(citations) / math.log1p(max_citations))

    def _recency_score(self, publish_date: str) -> float:
        year = extract_year(publish_date)
        if not year:
            return 0.45
        age = max(0, self.current_year - year)
        return max(0.20, 1.0 - min(age, 20) / 20)

    def _metadata_score(self, reference: ReferenceRecord) -> float:
        fields = [
            reference.title,
            reference.doi,
            reference.journal,
            reference.publish_date,
            reference.authors,
            reference.abstract,
            reference.citation_count is not None,
        ]
        return sum(bool(field) for field in fields) / len(fields)


class ReferenceAnalysisService:
    """Build a reference-paper pool, rank it, and optionally download top records."""

    def __init__(
        self,
        manifest_path: Path,
        out_dir: Path | None = None,
        papers_dir: Path | None = None,
        project_name: str = "",
        max_references_per_paper: int | None = 50,
        max_total_references: int | None = 1000,
        relevance_threshold: float = 0.30,
        max_reference_downloads: int = 0,
        min_value_score: float = 0.45,
        require_doi_for_download: bool = False,
        reference_query: str = "",
        metadata_sources: list[str] | None = None,
        metadata_timeout: int = 15,
        request_interval: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        sentence_model: str = "allenai-specter",
        embedder=None,
        metadata_enricher=None,
        downloader=None,
    ):
        self.manifest_path = Path(manifest_path)
        self.papers_dir = Path(papers_dir) if papers_dir else self.manifest_path.parent.parent / "papers"
        self.major_domain = major_domain_name(project_name)
        self.out_dir = (
            Path(out_dir)
            if out_dir
            else report_data_dir(self.manifest_path.parent.parent / "reports", self.major_domain) / "references"
        )
        self.max_references_per_paper = max_references_per_paper
        self.max_total_references = max_total_references
        self.relevance_threshold = relevance_threshold
        self.max_reference_downloads = max_reference_downloads
        self.min_value_score = min_value_score
        self.require_doi_for_download = require_doi_for_download
        self.reference_query = reference_query
        self.metadata_sources = metadata_sources or list(DEFAULT_REFERENCE_SOURCES)
        self.metadata_timeout = metadata_timeout
        self.request_interval = request_interval
        self.extractor = PdfReferenceExtractor()
        self.embedder = None if embedder is False else (embedder if embedder is not None else SentenceTransformerEmbedder(sentence_model))
        self.metadata_enricher = metadata_enricher
        self.downloader = downloader

    def run(self) -> list[ReferenceRecord]:
        articles = self.load_manifest()
        references = self.collect_references(articles)
        references = self.enrich_references(references)
        self.score_references(articles, references)
        references = sorted(references, key=lambda item: (-item.value_score, -item.relevance_score, item.title.lower()))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.write_outputs(references)
        self.download_top_references(references)
        self.write_outputs(references)
        return references

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def collect_references(self, articles: list[ArticleRecord]) -> list[ReferenceRecord]:
        references_by_key: dict[str, ReferenceRecord] = {}
        total_seen = 0
        for article in articles:
            refs = list(article.references)
            if not refs and article.pdf_status == "complete" and article.local_pdf_path:
                refs = self.extractor.extract_from_article(article, max_references=self.max_references_per_paper)
            if self.max_references_per_paper is not None:
                refs = refs[: self.max_references_per_paper]
            for reference in refs:
                if self.max_total_references is not None and total_seen >= self.max_total_references:
                    return list(references_by_key.values())
                total_seen += 1
                reference.source_article_doi = reference.source_article_doi or article.doi
                reference.source_article_title = reference.source_article_title or article.title
                key = reference_key(reference)
                if not key:
                    continue
                existing = references_by_key.get(key)
                if existing is None:
                    reference.source_article_titles = dedupe([reference.source_article_title])
                    reference.source_article_dois = dedupe([reference.source_article_doi])
                    reference.source_article_count = max(1, len(reference.source_article_titles))
                    references_by_key[key] = reference
                else:
                    self.merge_reference(existing, reference)
        return list(references_by_key.values())

    def merge_reference(self, target: ReferenceRecord, incoming: ReferenceRecord) -> ReferenceRecord:
        for field_name in ["title", "doi", "journal", "publish_date", "abstract", "pdf_url"]:
            if not getattr(target, field_name) and getattr(incoming, field_name):
                setattr(target, field_name, getattr(incoming, field_name))
        if incoming.authors and not target.authors:
            target.authors = list(incoming.authors)
        target.source_article_titles = dedupe(target.source_article_titles + [incoming.source_article_title])
        target.source_article_dois = dedupe(target.source_article_dois + [incoming.source_article_doi])
        target.source_article_count = max(1, len(target.source_article_titles))
        return target

    def enrich_references(self, references: list[ReferenceRecord]) -> list[ReferenceRecord]:
        enricher = self.metadata_enricher or ReferenceMetadataEnricher(
            self.out_dir,
            sources=self.metadata_sources,
            timeout=self.metadata_timeout,
            request_interval=self.request_interval,
        )
        enriched = []
        for reference in references:
            try:
                enriched.append(enricher.enrich_reference(reference))
            except Exception as exc:
                reference.error = f"metadata:{exc.__class__.__name__}"
                enriched.append(reference)
        return enriched

    def score_references(self, articles: list[ArticleRecord], references: list[ReferenceRecord]) -> None:
        relevance = ReferenceRelevanceScorer(
            threshold=self.relevance_threshold,
            query=self.reference_query,
            embedder=self.embedder,
        )
        profile_text = relevance.build_profile_text(articles)
        for reference in references:
            relevance.score(reference, profile_text)
        ReferenceValueScorer().score_batch(references)

    def download_top_references(self, references: list[ReferenceRecord]) -> None:
        if self.max_reference_downloads <= 0:
            return
        downloader = self.downloader or PdfDownloader(
            self.papers_dir,
            domain_path_func=lambda article: (self.major_domain, article_subdomain(article, "references")),
        )
        downloaded = 0
        for reference in references:
            if downloaded >= self.max_reference_downloads:
                break
            if reference.relevance_score < self.relevance_threshold:
                continue
            if reference.value_score < self.min_value_score:
                continue
            if self.require_doi_for_download and not reference.doi:
                continue
            article = ArticleRecord(
                title=reference.title,
                doi=reference.doi,
                journal=reference.journal,
                pdf_url=reference.pdf_url,
                article_type="reference",
                publish_date=reference.publish_date,
                authors=list(reference.authors),
                abstract=reference.abstract,
                citation_count=reference.citation_count,
                subdomain="References",
            )
            article = downloader.download(article)
            reference.pdf_url = article.pdf_url
            reference.local_pdf_path = article.local_pdf_path
            reference.download_status = article.download_status
            reference.pdf_status = article.pdf_status
            reference.error = article.error
            if article.pdf_status == "complete" and article.local_pdf_path:
                downloaded += 1

    def write_outputs(self, references: list[ReferenceRecord]) -> dict[str, Path]:
        paths = {
            "manifest": self.out_dir / "reference_manifest.json",
            "candidates": self.out_dir / "reference_candidates.csv",
            "top_papers": self.out_dir / "reference_top_papers.csv",
            "download_report": self.out_dir / "reference_download_report.csv",
            "summary": self.out_dir / "reference_summary.json",
        }
        with open(paths["manifest"], "w", encoding="utf-8") as handle:
            json.dump([reference.to_manifest_dict() for reference in references], handle, ensure_ascii=False, indent=2)
        fields = [
            "title", "doi", "journal", "publish_date", "citation_count", "citation_source",
            "source_article_count", "relevance_score", "value_score", "journal_tier",
            "download_status", "pdf_status",
        ]
        self._write_csv(paths["candidates"], references, fields)
        self._write_csv(paths["top_papers"], references[:50], fields)
        self._write_csv(paths["download_report"], references, ["title", "doi", "pdf_url", "local_pdf_path", "download_status", "pdf_status", "error"])
        with open(paths["summary"], "w", encoding="utf-8") as handle:
            json.dump(self.summary(references), handle, ensure_ascii=False, indent=2)
        return paths

    def summary(self, references: list[ReferenceRecord]) -> dict:
        return {
            "total_references": len(references),
            "relevant_references": int(sum(reference.relevance_score >= self.relevance_threshold for reference in references)),
            "downloaded_references": int(sum(bool(reference.pdf_status == "complete" and reference.local_pdf_path) for reference in references)),
            "relevance_threshold": float(self.relevance_threshold),
            "min_value_score": float(self.min_value_score),
            "max_reference_downloads": int(self.max_reference_downloads),
            "journal_tiers": dict(Counter(reference.journal_tier or "unmapped" for reference in references)),
        }

    def _write_csv(self, path: Path, references: list[ReferenceRecord], fields: list[str]) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for reference in references:
                row = reference.to_manifest_dict()
                writer.writerow({field: row.get(field, "") for field in fields})


def token_relevance(profile_text: str, reference_text: str) -> tuple[float, str]:
    profile_tokens = tokens(profile_text)
    reference_tokens = tokens(reference_text)
    if not profile_tokens or not reference_tokens:
        return 0.0, "missing profile/reference text"
    overlap = sorted(profile_tokens & reference_tokens)
    score = len(overlap) / max(1, min(len(profile_tokens), len(reference_tokens)))
    return min(1.0, score), "shared terms: " + ", ".join(overlap[:10]) if overlap else "no shared terms"


def tokens(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "into", "using",
        "study", "paper", "article", "research", "analysis", "nature",
    }
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", (text or "").casefold())
        if token not in stopwords
    }


def cosine_pair(embeddings) -> float:
    first = list(embeddings[0])
    second = list(embeddings[1])
    numerator = sum(a * b for a, b in zip(first, second))
    left = math.sqrt(sum(a * a for a in first))
    right = math.sqrt(sum(b * b for b in second))
    if left == 0 or right == 0:
        return 0.0
    return max(0.0, min(1.0, numerator / (left * right)))


def reference_key(reference: ReferenceRecord) -> str:
    if reference.doi:
        return "doi:" + reference.doi.casefold().strip()
    if reference.title:
        return "title:" + normalize(reference.title)
    return ""


def normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def extract_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value or "")
    return int(match.group(0)) if match else None


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


def run_from_args(args) -> int:
    service = ReferenceAnalysisService(
        Path(args.manifest),
        out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        papers_dir=Path(args.papers_dir) if getattr(args, "papers_dir", None) else None,
        project_name=getattr(args, "project_name", ""),
        max_references_per_paper=getattr(args, "max_references_per_paper", 50),
        max_total_references=getattr(args, "max_total_references", 1000),
        relevance_threshold=getattr(args, "reference_relevance_threshold", 0.30),
        max_reference_downloads=getattr(args, "max_reference_downloads", 0),
        min_value_score=getattr(args, "min_reference_value_score", 0.45),
        require_doi_for_download=getattr(args, "require_reference_doi", False),
        reference_query=getattr(args, "reference_query", ""),
        metadata_sources=getattr(args, "reference_sources", None),
        metadata_timeout=getattr(args, "metadata_timeout", 15),
        request_interval=getattr(args, "request_interval", DEFAULT_REQUEST_INTERVAL_SECONDS),
        sentence_model=getattr(args, "sentence_model", "allenai-specter"),
    )
    service.run()
    return 0

