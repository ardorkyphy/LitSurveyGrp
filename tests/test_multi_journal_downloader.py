# -*- coding: utf-8 -*-

import json

import pytest

from refchaser.multi_journal_downloader import (
    CrossrefJournalProvider,
    JournalConfig,
    LayeredJournalProvider,
    MultiJournalDownloadService,
    NatureCrawlerJournalProvider,
    OpenAlexJournalProvider,
    SUPPORTED_JOURNALS,
    list_supported_journals,
    parse_journal_specs,
    run_list_from_args,
    run_nature_aging_from_args,
    run_from_args,
)
from refchaser.filters import ArticleFilter
from refchaser.nature_aging_downloader import NatureJournalCrawler
from refchaser.paper_models import ArticleRecord
from refchaser.pdf_utils import PdfDownloader


LISTING_HTML = """
<html>
  <a href="/articles/s43587-026-01123-0">Nature Aging article</a>
  <a href="/articles/s41591-026-00001-0">Nature Medicine article</a>
  <a href="/articles/s41591-026-00001-0.pdf">PDF duplicate</a>
</html>
"""


DETAIL_HTML = """
<html>
  <head>
    <meta name="citation_title" content="A multi journal paper">
    <meta name="citation_doi" content="10.1038/example">
    <meta name="citation_article_type" content="Article">
    <meta name="citation_publication_date" content="2026/01/01">
    <meta name="citation_author" content="Alice Zhang">
    <meta name="citation_author_institution" content="Institute A">
    <meta name="citation_pdf_url" content="https://www.nature.com/articles/example.pdf">
    <meta name="description" content="This paper studies aging medicine.">
  </head>
</html>
"""


def test_supported_journals_contains_nature_aging():
    config = SUPPORTED_JOURNALS["nature-aging"]

    assert config.name == "Nature Aging"
    assert config.slug == "nataging"
    assert config.article_id_prefix == "s43587-"
    assert config.provider == "layered"
    assert config.issn == "2662-8465"


def test_supported_journals_contains_crossref_top_and_ccfa_entries():
    assert SUPPORTED_JOURNALS["science"].provider == "layered"
    assert SUPPORTED_JOURNALS["science"].issn == "0036-8075"
    assert SUPPORTED_JOURNALS["ijcv"].provider == "layered"
    assert SUPPORTED_JOURNALS["tpami"].group == "ccf-a-journal"


def test_list_supported_journals_can_filter_by_group():
    entries = list_supported_journals("ccf-a-journal")

    assert entries
    assert all(config.group == "ccf-a-journal" for _, config in entries)


def test_parse_journal_specs_accepts_builtin_and_custom_specs():
    configs = parse_journal_specs([
        "nature-aging",
        "Nature Test=ntest:s12345-",
        "Nature Open=nopen",
    ])

    assert configs[0].name == "Nature Aging"
    assert configs[1] == JournalConfig("Nature Test", "ntest", "s12345-", provider="nature")
    assert configs[2] == JournalConfig("Nature Open", "nopen", None, provider="nature")


def test_parse_journal_specs_accepts_api_custom_specs():
    configs = parse_journal_specs([
        "crossref:Test Journal=1234-5678",
        "openalex:Open Journal=1111-2222",
        "layered:Layered Journal=3333-4444",
    ])

    assert configs == [
        JournalConfig("Test Journal", provider="crossref", issn="1234-5678", group="custom"),
        JournalConfig("Open Journal", provider="openalex", issn="1111-2222", group="custom"),
        JournalConfig("Layered Journal", provider="layered", issn="3333-4444", group="custom"),
    ]


def test_parse_journal_specs_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_journal_specs(["unknown-journal"])


def test_nature_journal_crawler_filters_by_prefix_and_sets_journal():
    crawler = NatureJournalCrawler("Nature Aging", "nataging", article_id_prefix="s43587-")

    urls = crawler.parse_listing(LISTING_HTML)
    article = crawler.parse_article_detail(DETAIL_HTML, urls[0])

    assert urls == ["https://www.nature.com/articles/s43587-026-01123-0"]
    assert article.journal == "Nature Aging"


def test_multi_journal_service_wires_shared_pdf_downloader(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path / "中文路径",
        journals=[JournalConfig("Nature Aging", "nataging", "s43587-")],
        year=2026,
        limit=10,
        per_journal_limit=3,
        dry_run=True,
        download_timeout=9,
    )

    assert service.output_dir.name == "中文路径"
    assert isinstance(service.downloader, PdfDownloader)
    assert service.year == 2026
    assert service.limit == 10
    assert service.per_journal_limit == 3
    assert service.download_timeout == 9


class FakeCrossrefResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeCrossrefSession:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeCrossrefResponse(self.data)


def test_crossref_provider_discovers_article_records():
    data = {
        "message": {
            "items": [
                {
                    "title": ["A Crossref paper"],
                    "DOI": "10.1/crossref",
                    "container-title": ["Science"],
                    "URL": "https://doi.org/10.1/crossref",
                    "type": "journal-article",
                    "published-print": {"date-parts": [[2026, 1, 2]]},
                    "author": [
                        {
                            "given": "Alice",
                            "family": "Zhang",
                            "affiliation": [{"name": "Institute A"}],
                        }
                    ],
                    "abstract": "<jats:p>Abstract text.</jats:p>",
                    "link": [{"URL": "https://example.org/paper.pdf", "content-type": "application/pdf"}],
                }
            ]
        }
    }
    session = FakeCrossrefSession(data)
    provider = CrossrefJournalProvider(
        JournalConfig("Science", provider="crossref", issn="0036-8075"),
        year=2026,
        limit=5,
        session=session,
    )

    articles = provider.discover()

    assert len(articles) == 1
    assert articles[0].title == "A Crossref paper"
    assert articles[0].doi == "10.1/crossref"
    assert articles[0].journal == "Science"
    assert articles[0].pdf_url == "https://example.org/paper.pdf"
    assert articles[0].authors == ["Alice Zhang"]
    assert articles[0].institutions == ["Institute A"]
    assert articles[0].abstract == "Abstract text."
    assert session.calls[0][1]["params"]["filter"] == "type:journal-article,from-pub-date:2026-01-01,until-pub-date:2026-12-31"


def test_crossref_provider_builds_year_range_filter():
    provider = CrossrefJournalProvider(
        JournalConfig("Science", provider="crossref", issn="0036-8075"),
        from_year=2022,
        to_year=2024,
    )

    assert provider.build_params()["filter"] == "type:journal-article,from-pub-date:2022-01-01,until-pub-date:2024-12-31"


def test_openalex_provider_discovers_article_records():
    data = {
        "results": [
            {
                "title": "An OpenAlex paper",
                "doi": "https://doi.org/10.1007/test",
                "type": "article",
                "publication_date": "2026-01-02",
                "cited_by_count": 12,
                "primary_location": {
                    "pdf_url": "https://example.org/open.pdf",
                    "source": {"display_name": "International Journal of Computer Vision"},
                },
                "authorships": [
                    {
                        "author": {"display_name": "Alice Zhang"},
                        "institutions": [{"display_name": "Institute A"}],
                    }
                ],
            }
        ]
    }
    session = FakeCrossrefSession(data)
    provider = OpenAlexJournalProvider(
        JournalConfig("International Journal of Computer Vision", provider="openalex", issn="0920-5691"),
        year=2026,
        limit=5,
        session=session,
    )

    articles = provider.discover()

    assert len(articles) == 1
    assert articles[0].title == "An OpenAlex paper"
    assert articles[0].doi == "10.1007/test"
    assert articles[0].journal == "International Journal of Computer Vision"
    assert articles[0].pdf_url == "https://example.org/open.pdf"
    assert articles[0].citation_count == 12
    assert session.calls[0][1]["params"]["filter"] == "primary_location.source.issn:0920-5691,type:article,from_publication_date:2026-01-01,to_publication_date:2026-12-31"


def test_openalex_provider_builds_year_range_filter():
    provider = OpenAlexJournalProvider(
        JournalConfig("IJCV", provider="openalex", issn="0920-5691"),
        from_year=2022,
        to_year=2024,
    )

    assert provider.build_params()["filter"] == (
        "primary_location.source.issn:0920-5691,type:article,"
        "from_publication_date:2022-01-01,to_publication_date:2024-12-31"
    )


def test_openalex_provider_does_not_treat_doi_page_as_pdf():
    provider = OpenAlexJournalProvider(JournalConfig("IJCV", provider="openalex", issn="0920-5691"))
    article = provider.parse_item({
        "title": "DOI only OA paper",
        "doi": "https://doi.org/10.1007/example",
        "primary_location": {"source": {"display_name": "IJCV"}},
        "open_access": {"oa_url": "https://doi.org/10.1007/example"},
    })

    assert article.pdf_url == ""


def test_multi_journal_service_builds_crossref_source(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("Science", provider="crossref", issn="0036-8075")],
        per_journal_limit=3,
    )

    source = service.build_source(service.journals[0])

    assert isinstance(source, CrossrefJournalProvider)


def test_multi_journal_service_builds_openalex_source(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("International Journal of Computer Vision", provider="openalex", issn="0920-5691")],
        per_journal_limit=3,
    )

    source = service.build_source(service.journals[0])

    assert isinstance(source, OpenAlexJournalProvider)


def test_multi_journal_service_builds_layered_source_by_default(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[SUPPORTED_JOURNALS["nature-aging"]],
        per_journal_limit=3,
    )

    source = service.build_source(service.journals[0])

    assert isinstance(source, LayeredJournalProvider)


def test_multi_journal_service_builds_nature_crawler_source(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("Nature Test", "ntest", provider="nature")],
    )

    source = service.build_source(service.journals[0])

    assert isinstance(source, NatureCrawlerJournalProvider)


def test_layered_provider_deduplicates_and_records_provider_errors():
    class GoodProvider:
        def __init__(self, articles):
            self.articles = articles

        def discover(self):
            return self.articles

    class FailingProvider:
        def discover(self):
            raise RuntimeError("boom")

    provider = LayeredJournalProvider(
        JournalConfig("Layered", provider="layered", issn="1234-5678"),
        provider_factories=[
            lambda: GoodProvider([ArticleRecord(title="OpenAlex", doi="10.1/shared")]),
            lambda: FailingProvider(),
            lambda: GoodProvider([
                ArticleRecord(title="Duplicate", doi="10.1/shared"),
                ArticleRecord(title="Crossref only", doi="10.1/unique"),
            ]),
        ],
    )

    articles = provider.discover()

    assert [article.title for article in articles] == ["OpenAlex", "Crossref only"]
    assert provider.errors == ["FailingProvider:RuntimeError"]


def test_multi_journal_service_continues_when_one_journal_source_fails(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[
            JournalConfig("Broken", provider="openalex", issn="0000-0000"),
            JournalConfig("Working", provider="openalex", issn="1111-1111"),
        ],
        dry_run=True,
    )

    class BrokenProvider:
        def discover(self):
            raise RuntimeError("broken")

    class WorkingProvider:
        def discover(self):
            return [ArticleRecord(title="Working paper", journal="Working")]

    service.build_source = lambda journal: BrokenProvider() if journal.name == "Broken" else WorkingProvider()

    articles = service.run()

    assert [article.title for article in articles] == ["Working paper"]
    assert service.source_errors == ["Broken:BrokenProvider:RuntimeError"]


def test_multi_journal_service_dry_run_marks_articles_and_writes_outputs(tmp_path):
    results_dir = tmp_path / "results"
    service = MultiJournalDownloadService(
        output_dir=tmp_path / "papers",
        results_dir=results_dir,
        journals=[JournalConfig("Nature Aging", "nataging", "s43587-")],
        dry_run=True,
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(title="Paper one", doi="10.1/one", journal="Nature Aging"),
        ArticleRecord(title="Paper two", doi="10.1/two", journal="Nature Medicine"),
    ])

    articles = service.run()
    manifest = results_dir / "multi_journal_manifest.json"
    report = results_dir / "multi_journal_download_report.csv"
    data = json.loads(manifest.read_text(encoding="utf-8"))

    assert [article.download_status for article in articles] == ["dry_run", "dry_run"]
    assert manifest.exists()
    assert report.exists()
    assert not (tmp_path / "papers" / "multi_journal_manifest.json").exists()
    assert data[1]["journal"] == "Nature Medicine"


def test_multi_journal_service_can_write_nature_aging_compat_output_names(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[SUPPORTED_JOURNALS["nature-aging"]],
        dry_run=True,
        manifest_name="article_manifest.json",
        report_name="download_report.csv",
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(title="Paper one", doi="10.1/one", journal="Nature Aging"),
    ])

    service.run()

    assert (tmp_path / "article_manifest.json").exists()
    assert (tmp_path / "download_report.csv").exists()
    assert not (tmp_path / "multi_journal_manifest.json").exists()


def test_multi_journal_service_limit_counts_complete_pdfs_not_attempts(tmp_path):
    service = MultiJournalDownloadService(output_dir=tmp_path, journals=[JournalConfig("Nature Aging", "nataging")], limit=1)
    articles = [
        ArticleRecord(title="Skipped", doi="10/skip"),
        ArticleRecord(title="Complete", doi="10/one", local_pdf_path=tmp_path / "one.pdf"),
        ArticleRecord(title="Should not process", doi="10/two", local_pdf_path=tmp_path / "two.pdf"),
    ]
    service.iter_articles = lambda: iter(articles)

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

    assert [article.title for article in processed] == ["Skipped", "Complete"]


def test_multi_journal_service_can_skip_non_pdf_candidates(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("IJCV", provider="openalex", issn="0920-5691")],
        pdf_only_candidates=True,
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(title="No PDF", doi="10/no"),
        ArticleRecord(title="Has PDF", doi="10/pdf", pdf_url="https://example.org/paper.pdf"),
    ])

    def fake_download(article):
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        article.local_pdf_path = tmp_path / "paper.pdf"
        return article

    service.downloader.download = fake_download

    processed = service.run()

    assert processed[0].download_status == "skipped"
    assert processed[0].pdf_status == "missing_pdf_url"
    assert processed[1].download_status == "downloaded"


def test_multi_journal_service_filters_before_download_and_manifest(tmp_path):
    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("Nature Aging", "nataging")],
        dry_run=True,
        article_filter=ArticleFilter(keywords=["senescence"], article_types=["article"], from_year=2024, to_year=2026),
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(title="Senescence atlas", abstract="Cellular senescence.", article_type="Article", publish_date="2025/01/01"),
        ArticleRecord(title="Metabolism atlas", abstract="Mitochondrial metabolism.", article_type="Article", publish_date="2025/01/01"),
        ArticleRecord(title="Senescence news", abstract="Cellular senescence.", article_type="News", publish_date="2025/01/01"),
    ])

    processed = service.run()
    saved = json.loads((tmp_path / "multi_journal_manifest.json").read_text(encoding="utf-8"))

    assert [article.title for article in processed] == ["Senescence atlas"]
    assert [item["title"] for item in saved] == ["Senescence atlas"]


def test_multi_journal_service_can_enrich_citations_before_filtering(tmp_path):
    class FakeEnricher:
        def enrich_article(self, article):
            article.citation_count = 12 if article.title == "High citation paper" else 2
            article.citation_source = "openalex"
            return article

    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("Nature Aging", "nataging")],
        dry_run=True,
        article_filter=ArticleFilter(min_citations=10),
        prefilter_enricher=FakeEnricher(),
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(title="Low citation paper"),
        ArticleRecord(title="High citation paper"),
    ])

    processed = service.run()

    assert [article.title for article in processed] == ["High citation paper"]
    assert processed[0].citation_count == 12


def test_multi_journal_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        to = str(tmp_path / "papers")
        results_dir = str(tmp_path / "results")
        journal = ["nature-aging"]
        year = 2026
        from_year = None
        to_year = None
        limit = 1
        per_journal_limit = 2
        download_timeout = 7
        pdf_only_candidates = False
        dry_run = True
        keyword = ["aging"]
        article_type = ["Article"]
        min_citations = 3
        author = ["Alice"]
        institution = ["Institute"]
        filter_sources = ["openalex"]
        metadata_timeout = 7

    captured = {}

    def fake_run(self):
        captured["article_filter"] = self.article_filter
        captured["prefilter_enricher"] = self.prefilter_enricher
        return []

    monkeypatch.setattr(MultiJournalDownloadService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["article_filter"].keywords == ["aging"]
    assert captured["article_filter"].article_types == ["Article"]
    assert captured["article_filter"].min_citations == 3
    assert captured["prefilter_enricher"] is not None


def test_nature_aging_compat_cli_uses_multi_journal_service(monkeypatch, tmp_path):
    class Args:
        to = str(tmp_path / "papers")
        results_dir = str(tmp_path / "results")
        year = 2026
        from_year = None
        to_year = None
        limit = 1
        dry_run = True
        download_timeout = 15
        pdf_only_candidates = False
        keyword = []
        article_type = []
        min_citations = None
        author = []
        institution = []
        filter_sources = None
        metadata_timeout = 15

    captured = {}

    def fake_run(self):
        captured["output_dir"] = self.output_dir
        captured["results_dir"] = self.results_dir
        captured["journals"] = self.journals
        captured["manifest_name"] = self.manifest_name
        captured["report_name"] = self.report_name
        return []

    monkeypatch.setattr(MultiJournalDownloadService, "run", fake_run)

    assert run_nature_aging_from_args(Args()) == 0
    assert captured["output_dir"].name == "papers"
    assert captured["results_dir"].name == "results"
    assert captured["journals"] == [SUPPORTED_JOURNALS["nature-aging"]]
    assert captured["manifest_name"] == "article_manifest.json"
    assert captured["report_name"] == "download_report.csv"


def test_list_journals_cli_adapter_prints_catalog(capsys):
    class Args:
        group = "ccf-a-journal"

    assert run_list_from_args(Args()) == 0
    output = capsys.readouterr().out
    assert "tpami" in output
    assert "ccf-a-journal" in output
