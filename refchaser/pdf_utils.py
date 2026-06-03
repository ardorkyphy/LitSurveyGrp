# -*- coding: utf-8 -*-
"""
PDF path, download, and validation utilities for the MVP paper pipeline.

This module owns all filesystem-safe PDF handling, including Chinese paths.
"""

import re
import shutil
import os
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency
    fitz = None

from refchaser.paper_models import ArticleRecord, PdfValidationResult


PAYWALL_MARKERS = [
    "subscribe",
    "purchase",
    "log in",
    "login",
    "institutional access",
    "access this article",
]


class OpenAccessPdfResolver:
    """Resolve open-access PDF URLs from DOI metadata services."""

    def __init__(self, session=None, timeout: int = 15, unpaywall_email: str | None = None, core_api_key: str | None = None):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.unpaywall_email = unpaywall_email or os.environ.get("UNPAYWALL_EMAIL", "research-tool@example.com")
        self.core_api_key = core_api_key or os.environ.get("CORE_API_KEY")

    def resolve(self, article: ArticleRecord) -> str:
        """Return an open-access PDF URL if one can be found."""
        doi = self._clean_doi(article.doi)
        if not doi:
            return ""
        for resolver in [
            self.resolve_plos,
            self.resolve_mdpi,
            self.resolve_europe_pmc,
            self.resolve_unpaywall,
            self.resolve_core,
        ]:
            url = resolver(doi)
            if url and self._looks_like_pdf_url(url):
                return url
        return ""

    def resolve_plos(self, doi: str) -> str:
        """Return a deterministic PLOS PDF URL for PLOS DOI patterns."""
        if not doi.lower().startswith("10.1371/journal."):
            return ""
        return f"https://journals.plos.org/plosone/article/file?id={quote(doi)}&type=printable"

    def resolve_mdpi(self, doi: str) -> str:
        """Return an MDPI PDF URL for MDPI DOI patterns."""
        if not doi.lower().startswith("10.3390/"):
            return ""
        return f"https://www.mdpi.com/{doi}/pdf"

    def resolve_europe_pmc(self, doi: str) -> str:
        """Resolve PDFs from Europe PMC search metadata."""
        data = self._get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1},
        )
        results = data.get("resultList", {}).get("result", []) if data else []
        if not results:
            return ""
        result = results[0]
        for full_text in result.get("fullTextUrlList", {}).get("fullTextUrl", []) or []:
            url = full_text.get("url", "")
            document_style = (full_text.get("documentStyle") or "").lower()
            availability = (full_text.get("availabilityCode") or "").lower()
            if ("pdf" in document_style or self._looks_like_pdf_url(url)) and availability in {"oa", "f", ""}:
                return url
        pmcid = result.get("pmcid") or result.get("pmcId")
        if pmcid:
            return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
        return ""

    def resolve_unpaywall(self, doi: str) -> str:
        """Resolve PDFs from Unpaywall best OA location."""
        data = self._get_json(
            f"https://api.unpaywall.org/v2/{quote(doi)}",
            params={"email": self.unpaywall_email},
        )
        if not data:
            return ""
        locations = [data.get("best_oa_location") or {}] + list(data.get("oa_locations") or [])
        for location in locations:
            url = location.get("url_for_pdf") or ""
            if self._looks_like_pdf_url(url):
                return url
        return ""

    def resolve_core(self, doi: str) -> str:
        """Resolve PDFs from CORE when CORE_API_KEY is configured."""
        if not self.core_api_key:
            return ""
        data = self._get_json(
            "https://api.core.ac.uk/v3/search/works",
            params={"q": f'doi:"{doi}"', "limit": 1},
            headers={"Authorization": f"Bearer {self.core_api_key}"},
        )
        results = data.get("results", []) if data else []
        if not results:
            return ""
        result = results[0]
        return result.get("downloadUrl") or result.get("fullTextIdentifier") or ""

    def _get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception:
            return {}

    def _clean_doi(self, doi: str) -> str:
        return (doi or "").strip().removeprefix("https://doi.org/").lower()

    def _looks_like_pdf_url(self, url: str) -> bool:
        value = (url or "").lower()
        return bool(value) and (
            value.endswith(".pdf")
            or "/pdf/" in value
            or "/pdf" in value
            or "content/pdf" in value
            or "type=printable" in value
        )


class PdfPathBuilder:
    """Create stable output paths and filenames for downloaded papers."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def ensure_output_dirs(self) -> None:
        """Create required output directories such as all_papers/."""
        (self.output_dir / "all_papers").mkdir(parents=True, exist_ok=True)
        (self.output_dir / ".tmp").mkdir(parents=True, exist_ok=True)

    def build_pdf_path(self, article: ArticleRecord) -> Path:
        """Return the final PDF path for an article."""
        self.ensure_output_dirs()
        filename = self.build_pdf_filename(article)
        return self.output_dir / "all_papers" / filename

    def build_pdf_filename(self, article: ArticleRecord) -> str:
        """Build '(year,journal)title(author,institution).pdf' style filename."""
        year = self._year(article.publish_date)
        journal = self._journal_abbrev(article.journal)
        title = article.title or article.doi or "paper"
        author = self._first_author(article.authors)
        institution = self._primary_institution(article.institutions)
        prefix = self.sanitize_filename(f"（{year}，{journal}）", max_length=40)
        suffix = self.sanitize_filename(f"（{author}，{institution}）", max_length=80)
        max_total = 180
        max_title = max(20, max_total - len(prefix) - len(suffix))
        safe_title = self.sanitize_filename(title, max_length=max_title)
        return prefix + safe_title + suffix + ".pdf"

    def doi_pdf_path(self, article: ArticleRecord) -> Path | None:
        """Return the DOI-based compatibility path if it can be derived."""
        doi_part = article.doi.replace("/", "_").replace("\\", "_").strip()
        if not doi_part:
            return None
        return self.output_dir / "all_papers" / (self.sanitize_filename(doi_part) + ".pdf")

    def existing_pdf_path(self, article: ArticleRecord) -> Path | None:
        """Find an existing PDF for this article under current or compatible naming."""
        current = self.build_pdf_path(article)
        if current.exists():
            return current
        doi_path = self.doi_pdf_path(article)
        if doi_path and doi_path.exists():
            return doi_path
        semantic = self.find_semantic_variant(article)
        if semantic:
            return semantic
        return None

    def cleanup_duplicate_variants(self, article: ArticleRecord, keep_path: Path) -> None:
        """Remove older duplicate names for the same article while keeping keep_path."""
        candidates = []
        doi_path = self.doi_pdf_path(article)
        if doi_path:
            candidates.append(doi_path)
        candidates.extend(self.find_semantic_variants(article))
        keep_normalized = self._normalize_path(keep_path)
        for candidate in candidates:
            try:
                if candidate.exists() and self._normalize_path(candidate) != keep_normalized:
                    candidate.unlink()
            except OSError:
                pass

    def _normalize_path(self, path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    def find_semantic_variant(self, article: ArticleRecord) -> Path | None:
        """Find an older semantic-name variant for the same article title."""
        variants = self.find_semantic_variants(article)
        return variants[0] if variants else None

    def find_semantic_variants(self, article: ArticleRecord) -> list[Path]:
        """Find semantic-name variants for the same article title."""
        all_papers = self.output_dir / "all_papers"
        if not all_papers.exists() or not article.title:
            return []
        year = self._year(article.publish_date)
        journal = self._journal_abbrev(article.journal)
        prefix = self.sanitize_filename(f"（{year}，{journal}）", max_length=40)
        title_marker = self.sanitize_filename(article.title, max_length=40)
        matches = []
        for candidate in all_papers.glob("*.pdf"):
            name = candidate.name
            if name.startswith(prefix) and title_marker in name:
                matches.append(candidate)
        return sorted(matches)

    def sanitize_filename(self, value: str, max_length: int = 160) -> str:
        """Return a Windows-safe filename segment."""
        value = value.strip() or "paper"
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
        value = re.sub(r"\s+", " ", value).strip(" .")
        if not value:
            value = "paper"
        return value[:max_length]

    def _year(self, publish_date: str) -> str:
        match = re.search(r"(19|20)\d{2}", publish_date or "")
        return match.group(0) if match else "未知年份"

    def _journal_abbrev(self, journal: str) -> str:
        if (journal or "").lower() == "nature aging":
            return "NA"
        words = re.findall(r"[A-Za-z0-9]+", journal or "")
        return "".join(word[0].upper() for word in words) or "未知期刊"

    def _first_author(self, authors: list[str]) -> str:
        if not authors:
            return "未知作者"
        first = authors[0].strip()
        if "," in first:
            first = first.split(",", 1)[0].strip()
        return first or "未知作者"

    def _primary_institution(self, institutions: list[str]) -> str:
        if not institutions:
            return "未知机构"
        institution = institutions[0].split(",", 1)[0].strip()
        return institution or "未知机构"


class HtmlXmlToPdfConverter:
    """Convert HTML/XML article content into a local, readable PDF."""

    SUPPORTED_CONTENT_TYPES = ("html", "xml", "xhtml")

    def can_convert(self, content_type: str, first_chunk: bytes = b"") -> bool:
        value = (content_type or "").lower()
        if any(marker in value for marker in self.SUPPORTED_CONTENT_TYPES):
            return True
        sample = (first_chunk or b"").lstrip().lower()
        return sample.startswith(b"<!doctype html") or sample.startswith(b"<html") or sample.startswith(b"<?xml")

    def convert_bytes_to_pdf(self, content: bytes, article: ArticleRecord, output_path: Path) -> Path:
        """Convert raw HTML/XML bytes to a PDF file."""
        if fitz is None:
            raise RuntimeError("PyMuPDF is required for HTML/XML to PDF conversion")
        text = self.extract_text(content)
        self.write_text_pdf(text, article, output_path)
        return output_path

    def extract_text(self, content: bytes) -> str:
        """Extract readable text from HTML/XML bytes."""
        raw = content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def write_text_pdf(self, text: str, article: ArticleRecord, output_path: Path) -> None:
        """Write extracted text into a simple PDF."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        page = document.new_page()
        margin = 48
        line_height = 12
        y = margin
        width = page.rect.width - margin * 2
        lines = self._wrap_lines(self._compose_text(text, article), max_chars=96)
        for line in lines:
            if y > page.rect.height - margin:
                page = document.new_page()
                y = margin
            page.insert_textbox(
                fitz.Rect(margin, y, margin + width, y + line_height * 1.4),
                line,
                fontsize=10,
                fontname="helv",
            )
            y += line_height
        document.save(str(output_path))
        document.close()

    def _compose_text(self, text: str, article: ArticleRecord) -> str:
        parts = [
            article.title or "Untitled article",
            f"Journal: {article.journal}" if article.journal else "",
            f"DOI: {article.doi}" if article.doi else "",
            "Abstract",
            article.abstract or "",
            "Converted Article Text",
            text,
            "References",
        ]
        return "\n".join(part for part in parts if part)

    def _wrap_lines(self, text: str, max_chars: int) -> list[str]:
        lines = []
        for paragraph in (text or "").splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                lines.append("")
                continue
            while len(paragraph) > max_chars:
                split_at = paragraph.rfind(" ", 0, max_chars)
                if split_at <= 0:
                    split_at = max_chars
                lines.append(paragraph[:split_at].strip())
                paragraph = paragraph[split_at:].strip()
            lines.append(paragraph)
        return lines


class PdfDownloader:
    """Download a paper PDF only when preflight and validation pass."""

    def __init__(self, output_dir: Path, timeout: int = 60, min_size_bytes: int = 200_000, session=None):
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.min_size_bytes = min_size_bytes
        self.session = session or requests.Session()
        self.paths = PdfPathBuilder(self.output_dir)
        self.converter = HtmlXmlToPdfConverter()
        self.oa_resolver = OpenAccessPdfResolver(session=self.session, timeout=timeout)

    def preflight(self, article: ArticleRecord) -> PdfValidationResult:
        """Check headers/first bytes before committing to a full download."""
        if not article.pdf_url:
            return PdfValidationResult(False, "missing_pdf_url", "article has no PDF URL")
        try:
            response = self.session.get(article.pdf_url, stream=True, timeout=self.timeout)
            with closing(response):
                if response.status_code >= 400:
                    return PdfValidationResult(False, "http_error", f"HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").lower()
                first_chunk = next(response.iter_content(chunk_size=5), b"")
                looks_pdf = first_chunk.startswith(b"%PDF-") or "pdf" in content_type
                if not looks_pdf and self.converter.can_convert(content_type, first_chunk):
                    return PdfValidationResult(True, "preflight_convertible", f"content-type={content_type}")
                if not looks_pdf:
                    return PdfValidationResult(False, "not_pdf", f"content-type={content_type}")
        except Exception as exc:
            return PdfValidationResult(False, "preflight_failed", str(exc))
        return PdfValidationResult(True, "preflight_ok")

    def download_convertible_to_pdf(self, article: ArticleRecord) -> Path:
        """Download HTML/XML content and convert it to a temporary PDF."""
        self.paths.ensure_output_dirs()
        temp_name = self.paths.sanitize_filename(article.doi or article.title or "paper") + ".converted.pdf"
        temp_path = self.output_dir / ".tmp" / temp_name
        with self.session.get(article.pdf_url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            content = response.content
        return self.converter.convert_bytes_to_pdf(content, article, temp_path)

    def download_to_temp(self, article: ArticleRecord) -> Path:
        """Download the PDF URL to a temporary file."""
        self.paths.ensure_output_dirs()
        temp_name = self.paths.sanitize_filename(article.doi or article.title or "paper") + ".tmp"
        temp_path = self.output_dir / ".tmp" / temp_name
        with self.session.get(article.pdf_url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        handle.write(chunk)
        return temp_path

    def validate_pdf(self, pdf_path: Path, article: ArticleRecord) -> PdfValidationResult:
        """Check whether a temporary PDF looks like a complete paper."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return PdfValidationResult(False, "missing_file", "downloaded file does not exist")
        file_size = pdf_path.stat().st_size
        if file_size < self.min_size_bytes:
            return PdfValidationResult(False, "too_small", "PDF is below minimum size", file_size=file_size)
        with open(pdf_path, "rb") as handle:
            head = handle.read(5)
            if not head.startswith(b"%PDF-"):
                return PdfValidationResult(False, "not_pdf", "file does not start with %PDF-", file_size=file_size)
            sample = handle.read(256 * 1024)
        text = sample.decode("latin1", errors="ignore").lower()
        has_paywall_marker = any(marker in text for marker in PAYWALL_MARKERS)
        if has_paywall_marker:
            return PdfValidationResult(
                False,
                "paywalled_or_incomplete",
                "PDF sample contains access restriction markers",
                file_size=file_size,
                has_paywall_marker=True,
            )
        has_abstract = "abstract" in text
        has_references = "references" in text
        if not (has_abstract or has_references):
            return PdfValidationResult(
                False,
                "missing_paper_markers",
                "PDF sample does not contain Abstract or References",
                file_size=file_size,
            )
        return PdfValidationResult(
            True,
            "complete",
            file_size=file_size,
            has_abstract=has_abstract,
            has_references=has_references,
        )

    def save_if_complete(self, temp_path: Path, article: ArticleRecord) -> ArticleRecord:
        """Move a validated temporary file to its final location."""
        final_path = self.paths.build_pdf_path(article)
        if final_path.exists():
            self.paths.cleanup_duplicate_variants(article, final_path)
            article.local_pdf_path = final_path
            article.download_status = "skipped_existing"
            article.pdf_status = "complete"
            return article
        shutil.move(str(temp_path), str(final_path))
        article.local_pdf_path = final_path
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        return article

    def download(self, article: ArticleRecord) -> ArticleRecord:
        """Run preflight, temp download, validation, and final save."""
        final_path = self.paths.build_pdf_path(article)
        if final_path.exists():
            self.paths.cleanup_duplicate_variants(article, final_path)
            article.local_pdf_path = final_path
            article.download_status = "skipped_existing"
            article.pdf_status = "complete"
            article.error = ""
            return article
        doi_path = self.paths.doi_pdf_path(article)
        if doi_path and doi_path.exists():
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(doi_path), str(final_path))
            article.local_pdf_path = final_path
            article.download_status = "skipped_existing_renamed"
            article.pdf_status = "complete"
            article.error = ""
            return article
        semantic_variant = self.paths.find_semantic_variant(article)
        if semantic_variant and semantic_variant.exists():
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(semantic_variant), str(final_path))
            article.local_pdf_path = final_path
            article.download_status = "skipped_existing_renamed"
            article.pdf_status = "complete"
            article.error = ""
            return article
        self.resolve_open_access_pdf(article)
        preflight = self.preflight(article)
        should_force_resolve = article.pdf_resolution_status != "provider_no_pdf_url"
        if should_force_resolve and not preflight.is_complete and preflight.status in {"missing_pdf_url", "http_error", "not_pdf"}:
            if self.resolve_open_access_pdf(article, force=True):
                preflight = self.preflight(article)
        if not preflight.is_complete:
            article.download_status = "skipped"
            article.pdf_status = preflight.status
            article.error = preflight.reason
            return article
        temp_path = None
        try:
            if preflight.status == "preflight_convertible":
                temp_path = self.download_convertible_to_pdf(article)
                validation = PdfValidationResult(True, "complete", file_size=Path(temp_path).stat().st_size, has_abstract=True, has_references=True)
            else:
                temp_path = self.download_to_temp(article)
                validation = self.validate_pdf(temp_path, article)
            if not validation.is_complete:
                article.download_status = "skipped"
                article.pdf_status = validation.status
                article.error = validation.reason
                Path(temp_path).unlink(missing_ok=True)
                return article
            return self.save_if_complete(temp_path, article)
        except Exception as exc:
            article.download_status = "failed"
            article.pdf_status = "error"
            article.error = str(exc)
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
            return article

    def resolve_open_access_pdf(self, article: ArticleRecord, force: bool = False) -> bool:
        """Fill article.pdf_url from open-access resolvers when possible."""
        if article.pdf_url and not force:
            return False
        if article.pdf_resolution_status == "provider_no_pdf_url" and not force:
            return False
        resolved = self.oa_resolver.resolve(article)
        if not resolved:
            article.pdf_resolution_status = article.pdf_resolution_status or "oa_pdf_not_found"
            return False
        article.pdf_url = resolved
        article.pdf_resolution_status = "oa_pdf_resolved"
        return True
