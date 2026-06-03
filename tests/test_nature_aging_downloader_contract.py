# -*- coding: utf-8 -*-

from refchaser.nature_aging_downloader import (
    NatureAgingCrawler,
    NatureAgingDownloadService,
    run_from_args,
)
from refchaser.paper_models import ArticleRecord
from refchaser.pdf_utils import PdfDownloader


LISTING_HTML = """
<html>
  <a href="/articles/s43587-026-01123-0">Article one</a>
  <a href="/articles/s43587-026-01123-0.pdf">PDF duplicate</a>
  <a href="/articles/s43587-026-01124-1">Article two</a>
  <a href="/articles/s43587-026-01125-y">Article three</a>
</html>
"""

PAGINATED_LISTING_PAGE_ONE = """
<html>
  <a href="/articles/s43587-026-01123-0">Article one</a>
  <a href="/nataging/research-articles?page=2&searchType=journalSearch&sort=PubDate&year=2026" aria-label="Next page">2</a>
</html>
"""

PAGINATED_LISTING_PAGE_TWO = """
<html>
  <a href="/articles/s43587-026-01124-1">Article two</a>
</html>
"""

DETAIL_HTML = """
<html>
  <head>
    <meta name="citation_title" content="A complete Nature Aging paper">
    <meta name="citation_doi" content="10.1038/s43587-026-01123-0">
    <meta name="citation_article_type" content="Article">
    <meta name="citation_publication_date" content="2026/01/01">
    <meta name="citation_author" content="Alice Zhang">
    <meta name="citation_author" content="Bob Li">
    <meta name="citation_author_institution" content="Institute A">
    <meta name="citation_pdf_url" content="https://www.nature.com/articles/s43587-026-01123-0.pdf">
    <meta name="description" content="This paper studies aging biology.">
  </head>
</html>
"""


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, html_by_url):
        self.html_by_url = html_by_url
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(self.html_by_url[url])


def test_nature_aging_crawler_stores_filters():
    crawler = NatureAgingCrawler(year=2026, limit=20)

    assert crawler.JOURNAL == "Nature Aging"
    assert crawler.year == 2026
    assert crawler.limit == 20


def test_build_listing_urls_uses_year_filter():
    crawler = NatureAgingCrawler(year=2026)

    assert crawler.build_listing_urls() == ["https://www.nature.com/nataging/research-articles?year=2026"]


def test_parse_listing_extracts_article_urls_and_skips_pdf_links():
    crawler = NatureAgingCrawler(limit=10)

    urls = crawler.parse_listing(LISTING_HTML)

    assert urls == [
        "https://www.nature.com/articles/s43587-026-01123-0",
        "https://www.nature.com/articles/s43587-026-01124-1",
        "https://www.nature.com/articles/s43587-026-01125-y",
    ]


def test_parse_article_detail_extracts_metadata():
    crawler = NatureAgingCrawler()

    article = crawler.parse_article_detail(DETAIL_HTML, "https://www.nature.com/articles/s43587-026-01123-0")

    assert article.title == "A complete Nature Aging paper"
    assert article.doi == "10.1038/s43587-026-01123-0"
    assert article.article_type == "Article"
    assert article.publish_date == "2026/01/01"
    assert article.authors == ["Alice Zhang", "Bob Li"]
    assert article.institutions == ["Institute A"]
    assert article.pdf_url.endswith(".pdf")
    assert article.abstract == "This paper studies aging biology."


def test_discover_fetches_listing_and_details_with_limit():
    listing_url = "https://www.nature.com/nataging/research-articles?year=2026"
    session = FakeSession({
        listing_url: LISTING_HTML,
        "https://www.nature.com/articles/s43587-026-01123-0": DETAIL_HTML,
    })
    crawler = NatureAgingCrawler(year=2026, limit=1, session=session)

    articles = crawler.discover()

    assert len(articles) == 1
    assert articles[0].doi == "10.1038/s43587-026-01123-0"


def test_discover_follows_nature_pagination_links():
    first_url = "https://www.nature.com/nataging/research-articles?year=2026"
    second_url = "https://www.nature.com/nataging/research-articles?page=2&searchType=journalSearch&sort=PubDate&year=2026"
    session = FakeSession({
        first_url: PAGINATED_LISTING_PAGE_ONE,
        second_url: PAGINATED_LISTING_PAGE_TWO,
        "https://www.nature.com/articles/s43587-026-01123-0": DETAIL_HTML,
        "https://www.nature.com/articles/s43587-026-01124-1": DETAIL_HTML,
    })
    crawler = NatureAgingCrawler(year=2026, session=session)

    articles = crawler.discover()

    assert len(articles) == 2
    assert session.urls[:2] == [
        first_url,
        "https://www.nature.com/articles/s43587-026-01123-0",
    ]
    assert second_url in session.urls


def test_download_service_wires_crawler_and_downloader(tmp_path):
    service = NatureAgingDownloadService(
        output_dir=tmp_path / "中文论文",
        year=2026,
        limit=5,
        dry_run=True,
    )

    assert service.output_dir.name == "中文论文"
    assert service.year == 2026
    assert service.limit == 5
    assert service.dry_run is True
    assert isinstance(service.crawler, NatureAgingCrawler)
    assert isinstance(service.downloader, PdfDownloader)


def test_download_service_writes_manifest_and_report(tmp_path):
    service = NatureAgingDownloadService(output_dir=tmp_path)
    articles = [service.crawler.parse_article_detail(DETAIL_HTML, "https://www.nature.com/articles/s43587-026-01123-0")]

    manifest = service.write_manifest(articles)
    report = service.write_report(articles)

    assert manifest.exists()
    assert report.exists()
    assert "A complete Nature Aging paper" in manifest.read_text(encoding="utf-8")
    assert "download_status" in report.read_text(encoding="utf-8-sig")


def test_download_service_dry_run_marks_articles(tmp_path):
    service = NatureAgingDownloadService(output_dir=tmp_path, dry_run=True)
    service._iter_discovered_articles = lambda: iter([
        service.crawler.parse_article_detail(DETAIL_HTML, "https://www.nature.com/articles/s43587-026-01123-0")
    ])

    articles = service.run()

    assert articles[0].download_status == "dry_run"
    assert (tmp_path / "article_manifest.json").exists()
    assert (tmp_path / "download_report.csv").exists()


def test_download_service_limit_counts_complete_pdfs_not_attempts(tmp_path):
    service = NatureAgingDownloadService(output_dir=tmp_path, limit=2)
    articles = [
        ArticleRecord(title="Skipped", doi="10/skip"),
        ArticleRecord(title="Complete one", doi="10/one", local_pdf_path=tmp_path / "one.pdf"),
        ArticleRecord(title="Complete two", doi="10/two", local_pdf_path=tmp_path / "two.pdf"),
        ArticleRecord(title="Should not process", doi="10/three", local_pdf_path=tmp_path / "three.pdf"),
    ]
    service._iter_discovered_articles = lambda: iter(articles)

    def fake_download(article):
        if article.title == "Skipped":
            article.download_status = "skipped"
            article.pdf_status = "not_pdf"
            return article
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        return article

    service.downloader.download = fake_download

    processed = service.run()

    assert [article.title for article in processed] == ["Skipped", "Complete one", "Complete two"]


def test_download_cli_adapter_runs_service(monkeypatch, tmp_path):
    class Args:
        to = str(tmp_path)
        year = 2026
        limit = 1
        dry_run = True

    monkeypatch.setattr(NatureAgingDownloadService, "run", lambda self: [])

    assert run_from_args(Args()) == 0
