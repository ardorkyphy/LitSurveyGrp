# -*- coding: utf-8 -*-
"""
Nature Aging MVP downloader.

This module coordinates article discovery from Nature Aging and delegates PDF
handling to pdf_utils.
"""

import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from refchaser.paper_models import ArticleRecord
from refchaser.pdf_utils import PdfDownloader


class NatureAgingCrawler:
    """Discover Nature Aging articles and normalize them into ArticleRecord."""

    JOURNAL = "Nature Aging"
    BASE_URL = "https://www.nature.com"
    LISTING_URL = "https://www.nature.com/nataging/research-articles"

    def __init__(self, year: int | None = None, limit: int | None = None, session=None):
        self.year = year
        self.limit = limit
        self.session = session or requests.Session()

    def build_listing_urls(self) -> list[str]:
        """Return listing/search URLs that should be crawled."""
        if self.year:
            return [f"{self.LISTING_URL}?year={self.year}"]
        return [self.LISTING_URL]

    def fetch_listing(self, url: str) -> str:
        """Fetch one listing page and return HTML."""
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.text

    def parse_listing(self, html: str) -> list[str]:
        """Extract article detail URLs from a listing page."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not re.search(r"/articles/s43587-", href):
                continue
            if href.endswith(".pdf"):
                continue
            full_url = urljoin(self.BASE_URL, href.split("#")[0])
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)
        return urls

    def fetch_article_detail(self, article_url: str) -> str:
        """Fetch one article detail page and return HTML."""
        response = self.session.get(article_url, timeout=60)
        response.raise_for_status()
        return response.text

    def parse_article_detail(self, html: str, article_url: str) -> ArticleRecord:
        """Extract metadata and PDF URL from an article detail page."""
        soup = BeautifulSoup(html, "html.parser")
        title = self._meta_content(soup, "citation_title") or self._text_first(soup, ["h1"])
        doi = self._meta_content(soup, "citation_doi")
        article_type = self._meta_content(soup, "citation_article_type")
        publish_date = (
            self._meta_content(soup, "citation_publication_date")
            or self._meta_content(soup, "dc.date")
            or ""
        )
        abstract = self._abstract_text(soup)
        authors = [tag.get("content", "").strip() for tag in soup.find_all("meta", attrs={"name": "citation_author"})]
        authors = [author for author in authors if author]
        institutions = [
            tag.get("content", "").strip()
            for tag in soup.find_all("meta", attrs={"name": "citation_author_institution"})
        ]
        institutions = [inst for inst in institutions if inst]
        pdf_url = self._meta_content(soup, "citation_pdf_url") or self._find_pdf_url(soup, article_url)
        return ArticleRecord(
            title=title.strip(),
            doi=doi.strip(),
            journal=self.JOURNAL,
            article_url=article_url,
            pdf_url=pdf_url,
            article_type=article_type.strip(),
            publish_date=publish_date.strip(),
            authors=authors,
            institutions=institutions,
            abstract=abstract.strip(),
        )

    def discover(self) -> list[ArticleRecord]:
        """Return discovered Nature Aging articles."""
        article_urls = []
        for listing_url in self.build_listing_urls():
            article_urls.extend(self.parse_listing(self.fetch_listing(listing_url)))
        articles = []
        for article_url in article_urls:
            if self.limit and len(articles) >= self.limit:
                break
            articles.append(self.parse_article_detail(self.fetch_article_detail(article_url), article_url))
        return articles

    def _meta_content(self, soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        return tag.get("content", "") if tag else ""

    def _text_first(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                return " ".join(tag.get_text(" ", strip=True).split())
        return ""

    def _abstract_text(self, soup: BeautifulSoup) -> str:
        meta = self._meta_content(soup, "dc.description") or self._meta_content(soup, "description")
        if meta:
            return meta
        abstract = soup.find(id=re.compile("abstract", re.I)) or soup.select_one("[data-title='Abstract']")
        if abstract:
            return " ".join(abstract.get_text(" ", strip=True).split())
        return ""

    def _find_pdf_url(self, soup: BeautifulSoup, article_url: str) -> str:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True).lower()
            if href.endswith(".pdf") or "download pdf" in text or text == "pdf":
                return urljoin(self.BASE_URL, href)
        return article_url.rstrip("/") + ".pdf"


class NatureJournalCrawler(NatureAgingCrawler):
    """Configurable crawler for Nature journal article listing pages."""

    def __init__(
        self,
        journal_name: str,
        journal_slug: str,
        article_id_prefix: str | None = None,
        year: int | None = None,
        limit: int | None = None,
        session=None,
    ):
        super().__init__(year=year, limit=limit, session=session)
        self.JOURNAL = journal_name
        self.journal_name = journal_name
        self.journal_slug = journal_slug.strip("/")
        self.article_id_prefix = article_id_prefix
        self.LISTING_URL = f"{self.BASE_URL}/{self.journal_slug}/research-articles"

    def parse_listing(self, html: str) -> list[str]:
        """Extract article detail URLs from a Nature listing page."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf") or "/articles/" not in href:
                continue
            if self.article_id_prefix and self.article_id_prefix not in href:
                continue
            full_url = urljoin(self.BASE_URL, href.split("#")[0])
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)
        return urls

    def parse_article_detail(self, html: str, article_url: str) -> ArticleRecord:
        article = super().parse_article_detail(html, article_url)
        article.journal = self.journal_name
        return article


class NatureAgingDownloadService:
    """High-level service used by the command line entry point."""

    def __init__(
        self,
        output_dir: Path,
        year: int | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.year = year
        self.limit = limit
        self.dry_run = dry_run
        self.crawler = NatureAgingCrawler(year=year, limit=limit)
        self.downloader = PdfDownloader(self.output_dir)

    def run(self) -> list[ArticleRecord]:
        """Discover articles, then process until limit complete PDFs are available."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        articles = []
        complete_count = 0
        for article in self._iter_discovered_articles():
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

    def _iter_discovered_articles(self):
        """Yield discovered ArticleRecord instances without applying successful-download limit."""
        for listing_url in self.crawler.build_listing_urls():
            article_urls = self.crawler.parse_listing(self.crawler.fetch_listing(listing_url))
            for article_url in article_urls:
                yield self.crawler.parse_article_detail(self.crawler.fetch_article_detail(article_url), article_url)

    def write_manifest(self, articles: list[ArticleRecord]) -> Path:
        """Write article_manifest.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "article_manifest.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return path

    def write_report(self, articles: list[ArticleRecord]) -> Path:
        """Write download_report.csv."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "download_report.csv"
        fields = [
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


def run_from_args(args) -> int:
    """CLI adapter for python -m refchaser download-nature-aging."""
    service = NatureAgingDownloadService(
        output_dir=Path(args.to),
        year=args.year,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    service.run()
    return 0
