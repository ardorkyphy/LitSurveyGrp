# -*- coding: utf-8 -*-
"""
MVP RIS exporter.

This exporter converts normalized article and reference manifests into RIS.
"""

import json
import re
from pathlib import Path

from litsurveygrp.paper_models import ArticleRecord, ReferenceRecord


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "using", "both", "only",
    "aging", "age", "aged", "disease", "paper", "study", "article", "analysis", "a", "an",
    "of", "in", "to", "on", "by", "as", "is", "are", "via", "or",
}


class ReferenceRelevanceScorer:
    """Local relevance scorer for deciding which references belong in survey expansion."""

    def __init__(self, threshold: float = 0.12):
        self.threshold = threshold

    def score(self, source: ArticleRecord, reference: ReferenceRecord) -> ReferenceRecord:
        source_tokens = self._tokens(" ".join([
            source.title,
            source.abstract,
            source.subdomain,
            source.problem_statement,
            source.solution_summary or "",
        ]))
        reference_tokens = self._tokens(" ".join([reference.title, reference.abstract, reference.journal]))
        if not source_tokens or not reference_tokens:
            reference.relevance_score = 0.0
            reference.relevance_reason = "missing source/reference text"
            return reference
        overlap = sorted(source_tokens & reference_tokens)
        coverage = len(overlap) / max(1, min(len(source_tokens), len(reference_tokens)))
        score = self._score_with_domain_boost(coverage, overlap, reference_tokens)
        reference.relevance_score = round(score, 3)
        reference.relevance_reason = "shared terms: " + ", ".join(overlap[:10]) if overlap else "no shared domain terms"
        return reference

    def is_relevant(self, source: ArticleRecord, reference: ReferenceRecord) -> bool:
        scored = self.score(source, reference)
        return scored.relevance_score >= self.threshold

    def _tokens(self, text: str) -> set[str]:
        tokens = set()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", (text or "").lower()):
            if token not in STOPWORDS:
                tokens.add(token)
        return tokens

    def _score_with_domain_boost(self, coverage: float, overlap: list[str], reference_tokens: set[str]) -> float:
        domain_terms = {
            "alzheimer", "dementia", "apoe", "amyloid", "tau", "neurodegeneration",
            "aging", "ageing", "longevity", "senescence", "autophagy", "mitophagy",
            "peroxisome", "peroxisomal", "metabolic", "metabolism", "proteomic",
            "inflammaging", "macrophage", "fibrosis", "vascular", "mri",
        }
        domain_hits = sorted((set(overlap) | reference_tokens) & domain_terms)
        boost = min(0.08, 0.02 * len(domain_hits))
        return min(1.0, coverage + boost)


class RisExporter:
    """Export ArticleRecord entries to RIS."""

    def __init__(self, manifest_path: Path, output_path: Path | None = None):
        self.manifest_path = Path(manifest_path)
        self.output_path = Path(output_path) if output_path else self.manifest_path.parent / "source_papers.ris"

    def load_manifest(self) -> list[ArticleRecord]:
        """Read article_manifest.json or classified_manifest.json."""
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def should_export(self, article: ArticleRecord) -> bool:
        """Return True when a record is suitable for RIS export."""
        return bool(
            article.title
            and article.doi
            and article.local_pdf_path
            and article.pdf_status == "complete"
            and article.download_status in {
                "downloaded",
                "skipped_existing",
                "skipped_existing_renamed",
            }
        )

    def format_article(self, article: ArticleRecord) -> str:
        """Return one RIS record."""
        return self.format_record(
            title=article.title,
            doi=article.doi,
            journal=article.journal,
            publish_date=article.publish_date,
            authors=article.authors,
            abstract=article.abstract,
        )

    def format_reference(self, reference: ReferenceRecord) -> str:
        """Return one RIS record for a cited/reference paper."""
        return self.format_record(
            title=reference.title,
            doi=reference.doi,
            journal=reference.journal,
            publish_date=reference.publish_date,
            authors=reference.authors,
            abstract=reference.abstract,
        )

    def format_record(
        self,
        title: str,
        doi: str = "",
        journal: str = "",
        publish_date: str = "",
        authors: list[str] | None = None,
        abstract: str = "",
    ) -> str:
        """Return one RIS record."""
        lines = ["TY  - JOUR"]
        lines.append(f"TI  - {self._clean(title)}")
        for author in authors or []:
            lines.append(f"AU  - {self._clean(author)}")
        if publish_date:
            lines.append(f"PY  - {self._clean(publish_date[:4])}")
        if doi:
            lines.append(f"DO  - {self._clean(doi)}")
        if journal:
            lines.append(f"JF  - {self._clean(journal)}")
        if abstract:
            lines.append(f"AB  - {self._clean(abstract)}")
        lines.append("ER  -")
        return "\n".join(lines) + "\n"

    def export(self) -> Path:
        """Write the RIS file and return its path."""
        articles = [article for article in self.load_manifest() if self.should_export(article)]
        with open(self.output_path, "w", encoding="utf-8", newline="\n") as handle:
            for article in articles:
                handle.write(self.format_article(article))
                handle.write("\n")
        return self.output_path

    def export_summary(self) -> dict:
        """Return counts for exportable and skipped records."""
        articles = self.load_manifest()
        exportable = [article for article in articles if self.should_export(article)]
        return {
            "total_records": len(articles),
            "exported_records": len(exportable),
            "skipped_records": len(articles) - len(exportable),
            "output_path": str(self.output_path),
        }

    def _clean(self, value: str) -> str:
        return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


class ReferenceRisExporter(RisExporter):
    """Export relevant references from ArticleRecord.references to RIS."""

    def __init__(
        self,
        manifest_path: Path,
        output_path: Path | None = None,
        relevance_threshold: float = 0.12,
        max_records: int | None = None,
        require_doi: bool = False,
    ):
        super().__init__(
            manifest_path,
            output_path or Path(manifest_path).parent / "reference_papers.ris",
        )
        self.scorer = ReferenceRelevanceScorer(threshold=relevance_threshold)
        self.max_records = max_records
        self.require_doi = require_doi

    def iter_relevant_references(self) -> list[ReferenceRecord]:
        """Return deduplicated relevant references from all source articles."""
        references_by_key = {}
        for article in self.load_manifest():
            for reference in article.references:
                reference.source_article_doi = reference.source_article_doi or article.doi
                reference.source_article_title = reference.source_article_title or article.title
                self.scorer.score(article, reference)
                if reference.relevance_score < self.scorer.threshold:
                    continue
                if self.require_doi and not reference.doi:
                    continue
                key = (reference.doi or reference.title).lower()
                if not key:
                    continue
                existing = references_by_key.get(key)
                if existing is None or reference.relevance_score > existing.relevance_score:
                    references_by_key[key] = reference
        references = sorted(
            references_by_key.values(),
            key=lambda item: (-item.relevance_score, item.title.lower()),
        )
        if self.max_records is not None:
            references = references[:self.max_records]
        return references

    def export(self) -> Path:
        references = self.iter_relevant_references()
        with open(self.output_path, "w", encoding="utf-8", newline="\n") as handle:
            for reference in references:
                handle.write(self.format_reference(reference))
                handle.write("\n")
        return self.output_path

    def export_summary(self) -> dict:
        articles = self.load_manifest()
        total_references = sum(len(article.references) for article in articles)
        exported = len(self.iter_relevant_references())
        return {
            "total_source_articles": len(articles),
            "total_references": total_references,
            "exported_records": exported,
            "skipped_records": total_references - exported,
            "relevance_threshold": self.scorer.threshold,
            "max_records": self.max_records,
            "require_doi": self.require_doi,
            "output_path": str(self.output_path),
        }


def relevance_percent_to_threshold(value: float | None, default: float = 0.12) -> float:
    """Convert a command-line relevance percentage to an internal 0-1 threshold."""
    if value is None:
        return default
    if value < 0 or value > 100:
        raise ValueError("--relevance-percent must be between 0 and 100")
    return value / 100


def validate_max_records(value: int | None) -> int | None:
    """Validate an optional positive max-records argument."""
    if value is None:
        return None
    if value < 1:
        raise ValueError("--max-records must be a positive integer")
    return value


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp export-ris."""
    if getattr(args, "references", False):
        exporter = ReferenceRisExporter(
            Path(args.manifest),
            Path(args.out) if args.out else None,
            relevance_threshold=relevance_percent_to_threshold(getattr(args, "relevance_percent", None)),
            max_records=validate_max_records(getattr(args, "max_records", None)),
            require_doi=getattr(args, "require_doi", False),
        )
    else:
        exporter = RisExporter(Path(args.manifest), Path(args.out) if args.out else None)
    exporter.export()
    return 0

