# -*- coding: utf-8 -*-
"""
Shared data models for the MVP paper pipeline.

These models are intentionally small. They describe the data contract between:
- journal discovery/download
- PDF validation
- lightweight classification
- reference extraction and RIS export
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PdfValidationResult:
    """Result of checking whether a downloaded PDF looks like a complete paper."""

    is_complete: bool
    status: str
    reason: str = ""
    page_count: Optional[int] = None
    file_size: Optional[int] = None
    has_abstract: bool = False
    has_references: bool = False
    has_paywall_marker: bool = False


@dataclass
class ReferenceRecord:
    """A normalized record for one cited/reference paper."""

    title: str
    doi: str = ""
    journal: str = ""
    publish_date: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    relevance_score: float = 0.0
    relevance_reason: str = ""
    source_article_doi: str = ""
    source_article_title: str = ""

    def to_manifest_dict(self) -> dict:
        return {
            "title": self.title,
            "doi": self.doi,
            "journal": self.journal,
            "publish_date": self.publish_date,
            "authors": list(self.authors),
            "abstract": self.abstract,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
            "source_article_doi": self.source_article_doi,
            "source_article_title": self.source_article_title,
        }

    @classmethod
    def from_manifest_dict(cls, data: dict) -> "ReferenceRecord":
        return cls(
            title=data.get("title", ""),
            doi=data.get("doi", ""),
            journal=data.get("journal", ""),
            publish_date=data.get("publish_date", ""),
            authors=list(data.get("authors") or []),
            abstract=data.get("abstract", ""),
            relevance_score=float(data.get("relevance_score") or 0.0),
            relevance_reason=data.get("relevance_reason", ""),
            source_article_doi=data.get("source_article_doi", ""),
            source_article_title=data.get("source_article_title", ""),
        )


@dataclass
class ArticleRecord:
    """A normalized record for one discovered/downloaded paper."""

    title: str
    doi: str = ""
    journal: str = "Nature Aging"
    article_url: str = ""
    pdf_url: str = ""
    local_pdf_path: Optional[Path] = None
    article_type: str = ""
    publish_date: str = ""
    authors: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    abstract: str = ""
    subdomain: str = "Other"
    classification_confidence: float = 0.0
    classification_reason: str = ""
    problem_statement: str = ""
    solution_summary: Optional[str] = None
    citation_count: Optional[int] = None
    citation_source: str = ""
    abstract_source: str = ""
    metadata_sources: list[str] = field(default_factory=list)
    enrichment_status: str = ""
    download_status: str = "pending"
    pdf_status: str = "unchecked"
    error: str = ""
    pdf_resolution_status: str = ""
    references: list[ReferenceRecord] = field(default_factory=list)

    def to_manifest_dict(self) -> dict:
        """Return a JSON-serializable representation for manifest files."""
        data = {
            "title": self.title,
            "doi": self.doi,
            "journal": self.journal,
            "article_url": self.article_url,
            "pdf_url": self.pdf_url,
            "local_pdf_path": str(self.local_pdf_path) if self.local_pdf_path else "",
            "article_type": self.article_type,
            "publish_date": self.publish_date,
            "authors": list(self.authors),
            "institutions": list(self.institutions),
            "abstract": self.abstract,
            "subdomain": self.subdomain,
            "classification_confidence": self.classification_confidence,
            "classification_reason": self.classification_reason,
            "problem_statement": self.problem_statement,
            "solution_summary": self.solution_summary,
            "citation_count": self.citation_count,
            "citation_source": self.citation_source,
            "abstract_source": self.abstract_source,
            "metadata_sources": list(self.metadata_sources),
            "enrichment_status": self.enrichment_status,
            "download_status": self.download_status,
            "pdf_status": self.pdf_status,
            "error": self.error,
            "pdf_resolution_status": self.pdf_resolution_status,
            "references": [reference.to_manifest_dict() for reference in self.references],
        }
        return data

    @classmethod
    def from_manifest_dict(cls, data: dict) -> "ArticleRecord":
        """Build an ArticleRecord from one manifest entry."""
        local_pdf_path = data.get("local_pdf_path") or None
        return cls(
            title=data.get("title", ""),
            doi=data.get("doi", ""),
            journal=data.get("journal", "Nature Aging"),
            article_url=data.get("article_url", ""),
            pdf_url=data.get("pdf_url", ""),
            local_pdf_path=Path(local_pdf_path) if local_pdf_path else None,
            article_type=data.get("article_type", ""),
            publish_date=data.get("publish_date", ""),
            authors=list(data.get("authors") or []),
            institutions=list(data.get("institutions") or []),
            abstract=data.get("abstract", ""),
            subdomain=data.get("subdomain", "Other"),
            classification_confidence=float(data.get("classification_confidence") or 0.0),
            classification_reason=data.get("classification_reason", ""),
            problem_statement=data.get("problem_statement", ""),
            solution_summary=data.get("solution_summary"),
            citation_count=data.get("citation_count"),
            citation_source=data.get("citation_source", ""),
            abstract_source=data.get("abstract_source", ""),
            metadata_sources=list(data.get("metadata_sources") or []),
            enrichment_status=data.get("enrichment_status", ""),
            download_status=data.get("download_status", "pending"),
            pdf_status=data.get("pdf_status", "unchecked"),
            error=data.get("error", ""),
            pdf_resolution_status=data.get("pdf_resolution_status", ""),
            references=[
                ReferenceRecord.from_manifest_dict(reference)
                for reference in (data.get("references") or [])
            ],
        )
