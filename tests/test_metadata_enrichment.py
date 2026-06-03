# -*- coding: utf-8 -*-

import json

from refchaser.enrichment.metadata_enrichment import (
    CrossrefMetadataResolver,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    MetadataEnrichmentService,
    OpenAlexMetadataResolver,
    openalex_abstract,
    run_from_args,
)
from refchaser.paper_models import ArticleRecord


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.data)


class FakeResolver:
    def __init__(self, name, metadata):
        self.name = name
        self.metadata = metadata

    def resolve(self, article):
        return self.metadata


def test_openalex_abstract_reconstructs_inverted_index():
    assert openalex_abstract({"This": [0], "is": [1], "aging": [2]}) == "This is aging"


def test_openalex_resolver_parses_core_metadata():
    session = FakeSession({
        "title": "OpenAlex aging paper",
        "doi": "https://doi.org/10.1038/test",
        "type": "article",
        "publication_date": "2026-01-02",
        "cited_by_count": 42,
        "abstract_inverted_index": {"Aging": [0], "biology": [1]},
        "primary_location": {"source": {"display_name": "Nature Aging"}},
        "authorships": [
            {
                "author": {"display_name": "Alice Zhang"},
                "institutions": [{"display_name": "Institute A"}],
            }
        ],
    })
    resolver = OpenAlexMetadataResolver(session=session)

    metadata = resolver.resolve(ArticleRecord(title="Local title", doi="10.1038/test"))

    assert metadata["title"] == "OpenAlex aging paper"
    assert metadata["doi"] == "10.1038/test"
    assert metadata["journal"] == "Nature Aging"
    assert metadata["authors"] == ["Alice Zhang"]
    assert metadata["institutions"] == ["Institute A"]
    assert metadata["abstract"] == "Aging biology"
    assert metadata["citation_count"] == 42
    assert "doi:10.1038%2Ftest" in session.calls[0][0]


def test_crossref_resolver_parses_citation_count_and_abstract():
    session = FakeSession({
        "message": {
            "title": ["Crossref aging paper"],
            "DOI": "10.1/crossref",
            "container-title": ["Science"],
            "type": "journal-article",
            "published-online": {"date-parts": [[2026, 3, 4]]},
            "is-referenced-by-count": 7,
            "abstract": "<jats:p>Crossref abstract.</jats:p>",
            "author": [
                {
                    "given": "Alice",
                    "family": "Zhang",
                    "affiliation": [{"name": "Institute A"}],
                }
            ],
        }
    })
    resolver = CrossrefMetadataResolver(session=session)

    metadata = resolver.resolve(ArticleRecord(title="Local", doi="10.1/crossref"))

    assert metadata["citation_count"] == 7
    assert metadata["abstract"] == "Crossref abstract."
    assert metadata["authors"] == ["Alice Zhang"]
    assert metadata["institutions"] == ["Institute A"]


def test_metadata_enrichment_service_merges_sources_and_writes_manifest(tmp_path):
    manifest = tmp_path / "中文路径" / "manifest.json"
    manifest.parent.mkdir()
    article = ArticleRecord(title="Local aging title", doi="10.1/source")
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = MetadataEnrichmentService(
        manifest,
        resolvers=[
            FakeResolver("openalex", {"citation_count": 11, "journal": "Nature Aging"}),
            FakeResolver("semantic-scholar", {"abstract": "Semantic Scholar abstract.", "authors": ["Alice"]}),
        ],
        request_interval=0,
    )

    enriched = service.run()
    saved = json.loads((manifest.parent / "enriched_manifest.json").read_text(encoding="utf-8"))

    assert enriched[0].journal == "Nature Aging"
    assert enriched[0].citation_count == 11
    assert enriched[0].citation_source == "openalex"
    assert enriched[0].abstract == "Semantic Scholar abstract."
    assert enriched[0].abstract_source == "semantic-scholar"
    assert enriched[0].authors == ["Alice"]
    assert enriched[0].metadata_sources == ["openalex", "semantic-scholar"]
    assert enriched[0].enrichment_status == "enriched"
    assert saved[0]["citation_source"] == "openalex"


def test_metadata_enrichment_service_keeps_existing_abstract_source_priority():
    article = ArticleRecord(title="Paper", abstract="Existing abstract.", abstract_source="provider")
    service = MetadataEnrichmentService(
        "manifest.json",
        resolvers=[FakeResolver("semantic-scholar", {"abstract": "New abstract."})],
        request_interval=0,
    )

    enriched = service.enrich_article(article)

    assert enriched.abstract == "Existing abstract."
    assert enriched.abstract_source == "provider"
    assert enriched.metadata_sources == ["semantic-scholar"]


def test_metadata_enrichment_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        sources = ["openalex"]
        out = None
        timeout = 3
        request_interval = 5.0

    captured = {}

    def fake_run(self):
        captured["sources"] = self.sources
        captured["timeout"] = self.timeout
        captured["request_interval"] = self.request_interval
        return []

    monkeypatch.setattr(MetadataEnrichmentService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["sources"] == ["openalex"]
    assert captured["timeout"] == 3
    assert captured["request_interval"] == 5.0


def test_metadata_enrichment_default_request_interval_is_three_seconds():
    service = MetadataEnrichmentService("manifest.json", resolvers=[], sleep_func=lambda seconds: None)

    assert service.request_interval == DEFAULT_REQUEST_INTERVAL_SECONDS


def test_metadata_enrichment_service_throttles_between_resolver_calls():
    now = {"value": 100.0}
    sleeps = []

    def fake_monotonic():
        return now["value"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now["value"] += seconds

    service = MetadataEnrichmentService(
        "manifest.json",
        resolvers=[
            FakeResolver("openalex", {"citation_count": 1}),
            FakeResolver("crossref", {"journal": "Nature Aging"}),
        ],
        request_interval=3.0,
        sleep_func=fake_sleep,
        monotonic_func=fake_monotonic,
    )

    service.enrich_article(ArticleRecord(title="Paper"))

    assert sleeps == [3.0]


def test_metadata_enrichment_service_can_disable_throttle_for_tests():
    sleeps = []
    service = MetadataEnrichmentService(
        "manifest.json",
        resolvers=[
            FakeResolver("openalex", {"citation_count": 1}),
            FakeResolver("crossref", {"journal": "Nature Aging"}),
        ],
        request_interval=0,
        sleep_func=sleeps.append,
    )

    service.enrich_article(ArticleRecord(title="Paper"))

    assert sleeps == []
