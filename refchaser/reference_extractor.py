# -*- coding: utf-8 -*-
"""
MVP PDF reference extraction.

This module extracts a coarse reference list from downloaded PDFs and stores it
in ArticleRecord.references. It intentionally uses local text heuristics only.
"""

import json
import re
from pathlib import Path

from pypdf import PdfReader
try:
    import fitz
except ImportError:  # pragma: no cover - optional speed-up dependency
    fitz = None

from refchaser.paper_models import ArticleRecord, ReferenceRecord


class PdfReferenceExtractor:
    """Extract references from one PDF using text heuristics."""

    DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
    YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
    TAIL_PAGE_COUNT = 12

    def extract_text(self, pdf_path: Path) -> str:
        """Extract text from a PDF file."""
        if fitz is not None:
            return self._extract_text_with_pymupdf(pdf_path)
        return self._extract_text_with_pypdf(pdf_path)

    def _extract_text_with_pymupdf(self, pdf_path: Path) -> str:
        parts = []
        with fitz.open(str(pdf_path)) as document:
            for page in document:
                text = page.get_text("text") or ""
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def _extract_text_with_pypdf(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        parts = []
        start = max(0, len(reader.pages) - self.TAIL_PAGE_COUNT)
        for page in reader.pages[start:]:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
        return "\n".join(parts)

    def extract_reference_section(self, text: str) -> str:
        """Return text after the last References/Bibliography heading."""
        matches = list(re.finditer(r"(?im)^\s*(references|bibliography)\s*$", text or ""))
        if not matches:
            return ""
        section = text[matches[-1].end():]
        stop = re.search(r"(?im)^\s*(acknowledgements?|author contributions|competing interests|methods)\s*$", section)
        return section[:stop.start()] if stop else section

    def split_references(self, reference_section: str) -> list[str]:
        """Split a References section into individual reference strings."""
        section = re.sub(r"\r", "\n", reference_section or "")
        section = re.sub(r"(?<!\n)\n(?!\s*(\d+\.|\[\d+\]))", " ", section)
        chunks = re.split(r"(?m)^\s*(?:\d+\.|\[\d+\])\s+", section)
        refs = [self._clean_ref(chunk) for chunk in chunks if self._clean_ref(chunk)]
        if len(refs) > 1:
            return refs
        paragraphs = [self._clean_ref(item) for item in re.split(r"\n\s*\n", section) if self._clean_ref(item)]
        return paragraphs

    def parse_reference(self, raw_reference: str, source: ArticleRecord) -> ReferenceRecord:
        """Parse one raw reference string into a ReferenceRecord."""
        raw = self._clean_ref(raw_reference)
        doi = self._extract_doi(raw)
        year = self._extract_year(raw)
        authors = self._extract_authors(raw)
        title = self._extract_title(raw, authors, year, doi)
        journal = self._extract_journal(raw, title, year, doi)
        return ReferenceRecord(
            title=title or raw[:180],
            doi=doi,
            journal=journal,
            publish_date=year,
            authors=authors,
            source_article_doi=source.doi,
            source_article_title=source.title,
        )

    def extract_from_article(self, article: ArticleRecord, max_references: int | None = None) -> list[ReferenceRecord]:
        """Extract references from an ArticleRecord PDF path."""
        if not article.local_pdf_path:
            return []
        text = self.extract_text(Path(article.local_pdf_path))
        section = self.extract_reference_section(text)
        if not section:
            return []
        raw_references = self.split_references(section)
        if max_references:
            raw_references = raw_references[:max_references]
        return self._dedupe_references([self.parse_reference(raw, article) for raw in raw_references])

    def _extract_doi(self, raw: str) -> str:
        match = self.DOI_PATTERN.search(raw)
        if not match:
            return ""
        return match.group(0).rstrip(".,;)").lower()

    def _extract_year(self, raw: str) -> str:
        match = self.YEAR_PATTERN.search(raw)
        return match.group(0) if match else ""

    def _extract_authors(self, raw: str) -> list[str]:
        prefix = raw.split(". ", 1)[0].strip()
        if not prefix or len(prefix) > 160:
            return []
        return [item.strip() for item in re.split(r",\s+|;\s+", prefix) if item.strip()][:8]

    def _extract_title(self, raw: str, authors: list[str], year: str, doi: str) -> str:
        candidate = raw
        if doi:
            candidate = re.split(re.escape(doi), candidate, flags=re.I)[0]
        candidate = re.sub(r"https?://\S+", "", candidate)
        title_after_authors = self._title_after_author_prefix(candidate)
        if title_after_authors:
            return title_after_authors
        candidate = re.sub(r"\b([A-Z])\.", r"\1<dot>", candidate)
        parts = [item.strip(" .") for item in re.split(r"\.\s+", candidate) if item.strip(" .")]
        parts = [item.replace("<dot>", ".") for item in parts]
        if parts:
            first = parts[0]
            author_tail = re.search(r"(?:&|;)\s*[^.]+?\.\s*(.+)$", first)
            if author_tail and len(author_tail.group(1).split()) >= 3:
                return author_tail.group(1).strip(" .")
        for index, part in enumerate(parts):
            if index == 0 and ("," in part or "&" in part or " et al" in part.lower()):
                continue
            if len(part.split()) >= 3:
                return part
        return parts[1] if len(parts) > 1 else (parts[0] if parts else "")

    def _title_after_author_prefix(self, candidate: str) -> str:
        initials = r"(?:[A-Z]\.\s*){1,5}"
        surname = r"[^,.;]{2,50}"
        author_prefix = rf"^.+(?:et al\.|(?:&\s*)?{surname},\s*{initials})\s+"
        without_authors = re.sub(author_prefix, "", candidate, count=1).strip()
        if without_authors == candidate.strip():
            return ""
        title = re.split(r"\.\s+", without_authors, maxsplit=1)[0].strip(" .")
        if len(title.split()) >= 3:
            return title
        return ""

    def _extract_journal(self, raw: str, title: str, year: str, doi: str) -> str:
        candidate = raw
        if doi:
            candidate = re.split(re.escape(doi), candidate, flags=re.I)[0]
        if title:
            title_index = candidate.lower().find(title.lower())
            if title_index >= 0:
                candidate = candidate[title_index + len(title):]
        if year:
            candidate = re.split(r"\b" + re.escape(year) + r"\b", candidate, maxsplit=1)[0]
        candidate = re.sub(r"https?://\S+", "", candidate)
        candidate = candidate.strip(" .;:,()")
        match = re.match(r"([A-Z][A-Za-z&.\- ]{2,80}?)(?:\s+\d|,|$)", candidate)
        return self._clean_ref(match.group(1)).strip(" .") if match else ""

    def _dedupe_references(self, references: list[ReferenceRecord]) -> list[ReferenceRecord]:
        deduped = {}
        for reference in references:
            key = (reference.doi or reference.title).lower().strip()
            if not key:
                continue
            existing = deduped.get(key)
            if existing is None or self._record_quality(reference) > self._record_quality(existing):
                deduped[key] = reference
        return list(deduped.values())

    def _record_quality(self, reference: ReferenceRecord) -> int:
        return sum([
            bool(reference.title),
            bool(reference.doi),
            bool(reference.journal),
            bool(reference.publish_date),
            bool(reference.authors),
        ])

    def _clean_ref(self, value: str) -> str:
        return " ".join((value or "").replace("\n", " ").split()).strip()


class ReferenceExtractionService:
    """CLI-level service that updates a manifest with extracted references."""

    def __init__(self, manifest_path: Path, max_references_per_article: int | None = None):
        self.manifest_path = Path(manifest_path)
        self.max_references_per_article = max_references_per_article
        self.extractor = PdfReferenceExtractor()

    def run(self) -> list[ArticleRecord]:
        articles = self.load_manifest()
        for article in articles:
            if article.pdf_status != "complete" or not article.local_pdf_path:
                continue
            article.references = self.extractor.extract_from_article(
                article,
                max_references=self.max_references_per_article,
            )
        self.write_manifest(articles)
        return articles

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def write_manifest(self, articles: list[ArticleRecord]) -> Path:
        with open(self.manifest_path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return self.manifest_path


def run_from_args(args) -> int:
    service = ReferenceExtractionService(
        Path(args.manifest),
        max_references_per_article=args.max_references,
    )
    service.run()
    return 0
