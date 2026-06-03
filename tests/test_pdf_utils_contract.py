# -*- coding: utf-8 -*-

from pathlib import Path

from refchaser.paper_models import ArticleRecord
from refchaser.pdf_utils import HtmlXmlToPdfConverter, OpenAccessPdfResolver, PdfDownloader, PdfPathBuilder


class FakeResponse:
    def __init__(self, content=b"", status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.text = content.decode("latin1", errors="ignore")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index:index + chunk_size]

    def close(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses.pop(0)


class JsonResponse(FakeResponse):
    def __init__(self, data, status_code=200):
        super().__init__(b"", status_code=status_code, headers={"content-type": "application/json"})
        self.data = data

    def json(self):
        return self.data


class FailingSession:
    def get(self, url, **kwargs):
        raise AssertionError("network should not be called")


def test_pdf_path_builder_stores_path_object(tmp_path):
    builder = PdfPathBuilder(tmp_path / "中文目录")

    assert isinstance(builder.output_dir, Path)
    assert builder.output_dir.name == "中文目录"


def test_pdf_path_builder_creates_dirs_and_sanitizes_names(tmp_path):
    builder = PdfPathBuilder(tmp_path)

    builder.ensure_output_dirs()
    article = ArticleRecord(
        title="Bad",
        doi="10.1038/s43587-026-01123-0",
        journal="Nature Aging",
        publish_date="2026/05",
        authors=["Smith, Alice"],
        institutions=["Institute A, City"],
    )
    path = builder.build_pdf_path(article)

    assert (tmp_path / "all_papers").exists()
    assert (tmp_path / ".tmp").exists()
    assert path.name == "（2026，NA）Bad（Smith，Institute A）.pdf"
    assert builder.sanitize_filename('bad:name?.pdf') == "bad_name_.pdf"


def test_pdf_filename_truncates_title_but_preserves_metadata_suffix(tmp_path):
    builder = PdfPathBuilder(tmp_path)
    article = ArticleRecord(
        title="Very long title " * 30,
        journal="Nature Aging",
        publish_date="2026",
        authors=["Smith, Alice"],
        institutions=["Department of Aging Biology, University"],
    )

    filename = builder.build_pdf_filename(article)

    assert filename.startswith("（2026，NA）")
    assert filename.endswith("（Smith，Department of Aging Biology）.pdf")
    assert len(filename) < 230


def test_pdf_downloader_composes_path_builder(tmp_path):
    downloader = PdfDownloader(tmp_path, timeout=10, min_size_bytes=123)

    assert downloader.output_dir == tmp_path
    assert downloader.timeout == 10
    assert downloader.min_size_bytes == 123
    assert isinstance(downloader.paths, PdfPathBuilder)


def test_open_access_resolver_builds_plos_and_mdpi_pdf_urls():
    resolver = OpenAccessPdfResolver()

    assert resolver.resolve_plos("10.1371/journal.pone.1234567").startswith("https://journals.plos.org/")
    assert resolver.resolve_mdpi("10.3390/biology10100123") == "https://www.mdpi.com/10.3390/biology10100123/pdf"


def test_open_access_resolver_reads_europe_pmc_pdf_url():
    session = FakeSession([
        JsonResponse({
            "resultList": {
                "result": [
                    {
                        "fullTextUrlList": {
                            "fullTextUrl": [
                                {
                                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/article.pdf",
                                    "documentStyle": "pdf",
                                    "availabilityCode": "OA",
                                }
                            ]
                        }
                    }
                ]
            }
        })
    ])
    resolver = OpenAccessPdfResolver(session=session)

    assert resolver.resolve_europe_pmc("10.1000/test").endswith("article.pdf")


def test_open_access_resolver_reads_unpaywall_pdf_url():
    session = FakeSession([
        JsonResponse({
            "best_oa_location": {
                "url_for_pdf": "https://example.org/article.pdf",
            }
        })
    ])
    resolver = OpenAccessPdfResolver(session=session)

    assert resolver.resolve_unpaywall("10.1000/test") == "https://example.org/article.pdf"


def test_preflight_rejects_missing_pdf_url(tmp_path):
    downloader = PdfDownloader(tmp_path)
    result = downloader.preflight(ArticleRecord(title="Paper"))

    assert result.is_complete is False
    assert result.status == "missing_pdf_url"


def test_preflight_accepts_pdf_header(tmp_path):
    session = FakeSession([FakeResponse(b"%PDF-", headers={"content-type": "application/pdf"})])
    downloader = PdfDownloader(tmp_path, session=session)

    result = downloader.preflight(ArticleRecord(title="Paper", pdf_url="https://example.com/paper.pdf"))

    assert result.is_complete is True
    assert result.status == "preflight_ok"


def test_preflight_accepts_convertible_html(tmp_path):
    session = FakeSession([FakeResponse(b"<html>", headers={"content-type": "text/html"})])
    downloader = PdfDownloader(tmp_path, session=session)

    result = downloader.preflight(ArticleRecord(title="Paper", pdf_url="https://example.com/article"))

    assert result.is_complete is True
    assert result.status == "preflight_convertible"


def test_html_xml_converter_extracts_readable_text():
    converter = HtmlXmlToPdfConverter()

    text = converter.extract_text(b"<html><script>bad()</script><body><h1>Title</h1><p>Abstract text</p></body></html>")

    assert "Title" in text
    assert "Abstract text" in text
    assert "bad" not in text


def test_validate_pdf_rejects_too_small_file(tmp_path):
    pdf = tmp_path / "small.pdf"
    pdf.write_bytes(b"%PDF- tiny")
    downloader = PdfDownloader(tmp_path, min_size_bytes=200)

    result = downloader.validate_pdf(pdf, ArticleRecord(title="Paper"))

    assert result.is_complete is False
    assert result.status == "too_small"


def test_validate_pdf_accepts_basic_complete_pdf_marker(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-" + b"Abstract " + b"x" * 300 + b" References")
    downloader = PdfDownloader(tmp_path, min_size_bytes=100)

    result = downloader.validate_pdf(pdf, ArticleRecord(title="Paper"))

    assert result.is_complete is True
    assert result.status == "complete"
    assert result.has_abstract is True
    assert result.has_references is True


def test_download_saves_only_valid_pdf(tmp_path):
    content = b"%PDF-" + b"Abstract " + b"x" * 300 + b" References"
    session = FakeSession([
        FakeResponse(b"%PDF-", headers={"content-type": "application/pdf"}),
        FakeResponse(content, headers={"content-type": "application/pdf"}),
    ])
    downloader = PdfDownloader(tmp_path, min_size_bytes=100, session=session)

    article = downloader.download(
        ArticleRecord(
            title="中文论文",
            doi="10.1038/s43587-026-01123-0",
            journal="Nature Aging",
            publish_date="2026-05-01",
            authors=["Zhang, Wei"],
            institutions=["Institute of Aging, Beijing"],
            pdf_url="https://example.com/paper.pdf",
        )
    )

    assert article.download_status == "downloaded"
    assert article.pdf_status == "complete"
    assert article.local_pdf_path is not None
    assert article.local_pdf_path.exists()
    assert article.local_pdf_path.name == "（2026，NA）中文论文（Zhang，Institute of Aging）.pdf"


def test_download_resolves_missing_pdf_url_from_open_access_resolver(tmp_path):
    content = b"%PDF-" + b"Abstract " + b"x" * 300 + b" References"
    session = FakeSession([
        FakeResponse(b"%PDF-", headers={"content-type": "application/pdf"}),
        FakeResponse(content, headers={"content-type": "application/pdf"}),
    ])
    downloader = PdfDownloader(tmp_path, min_size_bytes=100, session=session)
    downloader.oa_resolver.resolve = lambda article: "https://example.org/open.pdf"

    article = downloader.download(
        ArticleRecord(
            title="OA paper",
            doi="10.1000/oa",
            journal="PLOS ONE",
            publish_date="2026",
        )
    )

    assert article.pdf_url == "https://example.org/open.pdf"
    assert article.download_status == "downloaded"
    assert article.pdf_status == "complete"


def test_download_skips_oa_resolution_when_provider_declares_no_pdf(tmp_path):
    downloader = PdfDownloader(tmp_path, session=FailingSession())
    downloader.oa_resolver.resolve = lambda article: (_ for _ in ()).throw(AssertionError("resolver should not be called"))

    article = downloader.download(
        ArticleRecord(
            title="No PDF paper",
            doi="10.1000/no-pdf",
            journal="IJCV",
            pdf_resolution_status="provider_no_pdf_url",
        )
    )

    assert article.download_status == "skipped"
    assert article.pdf_status == "missing_pdf_url"


def test_download_falls_back_to_open_access_pdf_after_http_error(tmp_path):
    content = b"%PDF-" + b"Abstract " + b"x" * 300 + b" References"
    session = FakeSession([
        FakeResponse(b"", status_code=403),
        FakeResponse(b"%PDF-", headers={"content-type": "application/pdf"}),
        FakeResponse(content, headers={"content-type": "application/pdf"}),
    ])
    downloader = PdfDownloader(tmp_path, min_size_bytes=100, session=session)
    downloader.oa_resolver.resolve = lambda article: "https://example.org/open.pdf"

    article = downloader.download(
        ArticleRecord(
            title="Fallback paper",
            doi="10.1000/fallback",
            journal="Cell",
            publish_date="2026",
            pdf_url="https://blocked.example/paper.pdf",
        )
    )

    assert session.urls[0] == "https://blocked.example/paper.pdf"
    assert article.pdf_url == "https://example.org/open.pdf"
    assert article.download_status == "downloaded"
    assert article.pdf_status == "complete"


def test_download_converts_html_article_to_pdf(tmp_path):
    html = b"""
    <html>
      <body>
        <h1>Converted article</h1>
        <p>Abstract: this article is available as HTML.</p>
        <h2>References</h2>
        <p>Smith, A. Reference paper. Journal 1, 1-2 (2024).</p>
      </body>
    </html>
    """
    session = FakeSession([
        FakeResponse(b"<html>", headers={"content-type": "text/html"}),
        FakeResponse(html, headers={"content-type": "text/html"}),
    ])
    downloader = PdfDownloader(tmp_path, min_size_bytes=1, session=session)

    article = downloader.download(
        ArticleRecord(
            title="Converted article",
            doi="10.1000/html",
            journal="Cell",
            publish_date="2026",
            authors=["Smith, Alice"],
            institutions=["Institute A"],
            abstract="this article is available as HTML.",
            pdf_url="https://example.com/article",
        )
    )

    assert article.download_status == "downloaded"
    assert article.pdf_status == "complete"
    assert article.local_pdf_path is not None
    assert article.local_pdf_path.exists()
    assert article.local_pdf_path.read_bytes().startswith(b"%PDF")


def test_download_skips_existing_pdf_before_network_call(tmp_path):
    existing = tmp_path / "all_papers" / "（2026，NA）Existing paper（Smith，Institute）.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"%PDF- existing")
    downloader = PdfDownloader(tmp_path, session=FailingSession())

    article = downloader.download(
        ArticleRecord(
            title="Existing paper",
            doi="10.1038/s43587-026-01122-1",
            journal="Nature Aging",
            publish_date="2026",
            authors=["Smith, A."],
            institutions=["Institute, City"],
            pdf_url="https://example.com/paper.pdf",
        )
    )

    assert article.download_status == "skipped_existing"
    assert article.pdf_status == "complete"
    assert article.local_pdf_path == existing


def test_download_renames_doi_named_existing_pdf_before_network_call(tmp_path):
    doi_named = tmp_path / "all_papers" / "10.1038_s43587-026-01122-1.pdf"
    doi_named.parent.mkdir(parents=True)
    doi_named.write_bytes(b"%PDF- existing")
    downloader = PdfDownloader(tmp_path, session=FailingSession())

    article = downloader.download(
        ArticleRecord(
            title="Renamed paper",
            doi="10.1038/s43587-026-01122-1",
            journal="Nature Aging",
            publish_date="2026",
            authors=["Author, A."],
            institutions=["Institution, City"],
            pdf_url="https://example.com/paper.pdf",
        )
    )

    expected = tmp_path / "all_papers" / "（2026，NA）Renamed paper（Author，Institution）.pdf"
    assert article.download_status == "skipped_existing_renamed"
    assert article.pdf_status == "complete"
    assert article.local_pdf_path == expected
    assert expected.exists()
    assert not doi_named.exists()


def test_download_cleans_old_semantic_variant_when_final_exists(tmp_path):
    final_path = tmp_path / "all_papers" / "（2026，NA）Urinary detection（Hartono，Department）.pdf"
    old_variant = tmp_path / "all_papers" / "（2026，NA）Urinary detection（Hartono，Department and.pdf"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"%PDF- final")
    old_variant.write_bytes(b"%PDF- duplicate")
    downloader = PdfDownloader(tmp_path, session=FailingSession())

    article = ArticleRecord(
        title="Urinary detection",
        doi="10.1038/s43587-026-01116-z",
        journal="Nature Aging",
        publish_date="2026",
        authors=["Hartono, Muhamad"],
        institutions=["Department, City"],
        pdf_url="https://example.com/paper.pdf",
    )

    result = downloader.download(article)

    assert result.download_status == "skipped_existing"
    assert result.local_pdf_path == final_path
    assert final_path.exists()
    assert not old_variant.exists()
