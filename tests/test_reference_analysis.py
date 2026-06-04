# -*- coding: utf-8 -*-

import csv
import json

from refchaser.paper_models import ArticleRecord, ReferenceRecord
from refchaser.reference_analysis import (
    JournalTierScorer,
    ReferenceAnalysisService,
    ReferenceMetadataEnricher,
    ReferenceRelevanceScorer,
    ReferenceValueScorer,
    cosine_pair,
    reference_key,
    run_from_args,
    token_relevance,
)


class FakeEmbedder:
    name = "specter:fake"

    def can_embed(self):
        return True

    def embed(self, texts):
        return [[1.0, 0.0], [0.8, 0.2]]


class FakeMetadataEnricher:
    def enrich_reference(self, reference):
        if reference.doi == "10.1/high":
            reference.journal = "Nature"
            reference.publish_date = "2024"
            reference.citation_count = 100
            reference.citation_source = "openalex"
            reference.abstract = "Senescence immune aging mechanisms."
            reference.metadata_sources = ["openalex"]
        elif reference.doi == "10.1/low":
            reference.journal = "Unknown Journal"
            reference.publish_date = "1999"
            reference.citation_count = 1
            reference.citation_source = "crossref"
        return reference


class FakeDownloader:
    def download(self, article):
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        article.local_pdf_path = "reference.pdf"
        return article


def test_reference_record_round_trips_extended_fields():
    reference = ReferenceRecord(
        title="Reference",
        doi="10.1/x",
        citation_count=12,
        citation_source="openalex",
        citation_counts={"openalex": 12},
        metadata_sources=["openalex"],
        relevance_score=0.5,
        value_score=0.7,
        journal_tier="top_general",
        journal_tier_score=1.0,
        source_article_count=2,
        source_article_titles=["A", "B"],
        source_article_dois=["10/a", "10/b"],
        pdf_url="https://example.org/ref.pdf",
        local_pdf_path="refs/ref.pdf",
        download_status="downloaded",
        pdf_status="complete",
    )

    loaded = ReferenceRecord.from_manifest_dict(reference.to_manifest_dict())

    assert loaded.citation_count == 12
    assert loaded.citation_counts == {"openalex": 12}
    assert loaded.metadata_sources == ["openalex"]
    assert loaded.value_score == 0.7
    assert loaded.journal_tier == "top_general"
    assert loaded.source_article_count == 2
    assert str(loaded.local_pdf_path).endswith("ref.pdf")
    assert loaded.pdf_status == "complete"


def test_journal_tier_scorer_maps_top_and_unknown_journals():
    scorer = JournalTierScorer()

    assert scorer.score("Nature") == ("top_general", 1.0)
    assert scorer.score("Nature Aging")[0] == "top_field"
    assert scorer.score("Small Specialist Journal") == ("unmapped", 0.45)


def test_relevance_scorer_uses_embedder_when_available():
    scorer = ReferenceRelevanceScorer(embedder=FakeEmbedder())
    reference = ReferenceRecord(title="Senescence reference")

    scored = scorer.score(reference, "aging profile")

    assert scored.relevance_score == round(cosine_pair([[1.0, 0.0], [0.8, 0.2]]), 3)
    assert scored.relevance_reason == "SPECTER cosine similarity"


def test_token_relevance_fallback_reports_shared_terms():
    score, reason = token_relevance("immune senescence aging", "senescence immune cells")

    assert score > 0
    assert "immune" in reason


def test_value_scorer_includes_journal_tier_and_metadata():
    reference = ReferenceRecord(
        title="High value",
        doi="10.1/high",
        journal="Nature",
        publish_date="2024",
        abstract="Abstract",
        authors=["Alice"],
        citation_count=100,
        relevance_score=0.8,
        source_article_count=3,
    )

    ReferenceValueScorer(current_year=2026).score(reference, max_citations=100)

    assert reference.journal_tier == "top_general"
    assert reference.value_score > 0.75
    assert "journal=top_general" in reference.value_reason


def test_reference_analysis_collects_dedupes_scores_and_writes_outputs(tmp_path):
    manifest = tmp_path / "classified_manifest.json"
    article = ArticleRecord(
        title="Source senescence immune paper",
        doi="10.1/source",
        abstract="This source studies immune senescence.",
        references=[
            ReferenceRecord(title="High ref", doi="10.1/high", source_article_title="Source senescence immune paper"),
            ReferenceRecord(title="High duplicate", doi="10.1/high", source_article_title="Source senescence immune paper"),
            ReferenceRecord(title="Low ref", doi="10.1/low"),
        ],
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = ReferenceAnalysisService(
        manifest,
        out_dir=tmp_path / "references",
        max_references_per_paper=10,
        max_total_references=10,
        relevance_threshold=0.1,
        max_reference_downloads=1,
        min_value_score=0.1,
        embedder=False,
        metadata_enricher=FakeMetadataEnricher(),
        downloader=FakeDownloader(),
    )

    references = service.run()
    saved = json.loads((tmp_path / "references" / "reference_manifest.json").read_text(encoding="utf-8"))
    candidates = read_csv(tmp_path / "references" / "reference_candidates.csv")
    summary = json.loads((tmp_path / "references" / "reference_summary.json").read_text(encoding="utf-8"))

    assert len(references) == 2
    assert references[0].doi == "10.1/high"
    assert references[0].value_score >= references[1].value_score
    assert references[0].pdf_status == "complete"
    assert saved[0]["journal_tier"] == "top_general"
    assert candidates[0]["doi"] == "10.1/high"
    assert summary["total_references"] == 2
    assert summary["downloaded_references"] == 1


def test_reference_analysis_respects_max_total_references(tmp_path):
    manifest = tmp_path / "manifest.json"
    article = ArticleRecord(
        title="Source",
        references=[
            ReferenceRecord(title="One", doi="10.1/one"),
            ReferenceRecord(title="Two", doi="10.1/two"),
        ],
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = ReferenceAnalysisService(
        manifest,
        max_total_references=1,
        max_reference_downloads=0,
        embedder=False,
        metadata_enricher=FakeMetadataEnricher(),
    )

    references = service.run()

    assert len(references) == 1


def test_reference_metadata_enricher_maps_article_fields(monkeypatch, tmp_path):
    class FakeService:
        def enrich_article(self, article):
            article.title = "Enriched"
            article.journal = "Nature"
            article.citation_count = 9
            article.metadata_sources = ["openalex"]
            return article

    enricher = ReferenceMetadataEnricher(tmp_path)
    enricher.service = FakeService()

    reference = enricher.enrich_reference(ReferenceRecord(title="Raw", doi="10.1/raw"))

    assert reference.title == "Enriched"
    assert reference.journal == "Nature"
    assert reference.citation_count == 9
    assert reference.metadata_sources == ["openalex"]


def test_reference_analysis_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        out_dir = str(tmp_path / "references")
        max_references_per_paper = 20
        max_total_references = 200
        reference_relevance_threshold = 0.4
        max_reference_downloads = 5
        min_reference_value_score = 0.6
        require_reference_doi = True
        reference_query = "immune aging"
        reference_sources = ["openalex"]
        metadata_timeout = 8
        request_interval = 1.5
        sentence_model = "allenai-specter"

    captured = {}

    def fake_run(self):
        captured["out_dir"] = self.out_dir
        captured["max_references_per_paper"] = self.max_references_per_paper
        captured["max_total_references"] = self.max_total_references
        captured["threshold"] = self.relevance_threshold
        captured["max_downloads"] = self.max_reference_downloads
        captured["min_value"] = self.min_value_score
        captured["require_doi"] = self.require_doi_for_download
        captured["query"] = self.reference_query
        captured["sources"] = self.metadata_sources
        return []

    monkeypatch.setattr(ReferenceAnalysisService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["out_dir"].name == "references"
    assert captured["max_references_per_paper"] == 20
    assert captured["max_total_references"] == 200
    assert captured["threshold"] == 0.4
    assert captured["max_downloads"] == 5
    assert captured["min_value"] == 0.6
    assert captured["require_doi"] is True
    assert captured["query"] == "immune aging"
    assert captured["sources"] == ["openalex"]


def test_reference_key_prefers_doi():
    assert reference_key(ReferenceRecord(title="A", doi="10.1/X")) == "doi:10.1/x"


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
