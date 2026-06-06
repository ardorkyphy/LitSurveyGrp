# -*- coding: utf-8 -*-

from pathlib import Path

from litsurveygrp.paper_models import ArticleRecord, PdfValidationResult, ReferenceRecord


def test_article_record_defaults_are_mvp_contract():
    article = ArticleRecord(title="Aging intervention study")

    assert article.title == "Aging intervention study"
    assert article.journal == ""
    assert article.subdomain == "Other"
    assert article.classification_confidence == 0.0
    assert article.classification_reason == ""
    assert article.download_status == "pending"
    assert article.pdf_status == "unchecked"
    assert article.authors == []
    assert article.institutions == []
    assert article.references == []
    assert article.solution_summary is None
    assert article.citation_source == ""
    assert article.citation_counts == {}
    assert article.citation_policy == ""
    assert article.abstract_source == ""
    assert article.metadata_sources == []
    assert article.enrichment_status == ""
    assert article.authoritative_topics == []


def test_article_record_list_defaults_are_not_shared():
    first = ArticleRecord(title="First")
    second = ArticleRecord(title="Second")

    first.authors.append("Alice")
    first.institutions.append("Institute A")

    assert second.authors == []
    assert second.institutions == []


def test_article_record_accepts_chinese_pdf_path():
    path = Path(r"D:\lky\school\science\论文\论文一.pdf")
    article = ArticleRecord(title="Paper", local_pdf_path=path)

    assert article.local_pdf_path == path


def test_article_record_manifest_round_trip_with_path():
    article = ArticleRecord(
        title="Paper",
        doi="10.1038/s43587-026-01123-0",
        local_pdf_path=Path(r"D:\论文\paper.pdf"),
        authors=["Alice", "Bob"],
        institutions=["Institute A"],
        download_status="downloaded",
        pdf_status="complete",
        citation_count=23,
        citation_source="openalex",
        citation_counts={"openalex": 23, "crossref": 7},
        citation_policy="max_available",
        abstract_source="semantic-scholar",
        metadata_sources=["openalex", "semantic-scholar"],
        enrichment_status="enriched",
        classification_confidence=0.81,
        classification_reason="profile=Mechanism_Research",
        classification_source="pubmed_mesh",
        classification_source_label="Alzheimer Disease",
        classification_taxonomy="MeSH",
        classification_evidence=[
            {
                "source": "pubmed_mesh",
                "taxonomy": "MeSH",
                "label": "Alzheimer Disease",
                "domain": "Alzheimer Disease",
                "confidence": 0.95,
            }
        ],
        authoritative_topics=[
            {
                "source": "openalex",
                "taxonomy": "OpenAlex Topics",
                "label": "Computer Science > Artificial Intelligence > Causal Learning",
                "field": "Computer Science",
                "subfield": "Artificial Intelligence",
                "topic": "Causal Learning",
            }
        ],
        references=[
            ReferenceRecord(
                title="Cited aging mechanism paper",
                doi="10.1/ref",
                authors=["Ref Author"],
                relevance_score=0.5,
                relevance_reason="shared terms: aging",
            )
        ],
    )

    data = article.to_manifest_dict()
    restored = ArticleRecord.from_manifest_dict(data)

    assert data["local_pdf_path"] == r"D:\论文\paper.pdf"
    assert restored.title == article.title
    assert restored.doi == article.doi
    assert restored.local_pdf_path == article.local_pdf_path
    assert restored.authors == ["Alice", "Bob"]
    assert restored.institutions == ["Institute A"]
    assert restored.download_status == "downloaded"
    assert restored.pdf_status == "complete"
    assert restored.citation_count == 23
    assert restored.citation_source == "openalex"
    assert restored.citation_counts == {"openalex": 23, "crossref": 7}
    assert restored.citation_policy == "max_available"
    assert restored.abstract_source == "semantic-scholar"
    assert restored.metadata_sources == ["openalex", "semantic-scholar"]
    assert restored.enrichment_status == "enriched"
    assert restored.classification_confidence == 0.81
    assert restored.classification_reason == "profile=Mechanism_Research"
    assert restored.classification_source == "pubmed_mesh"
    assert restored.classification_source_label == "Alzheimer Disease"
    assert restored.classification_taxonomy == "MeSH"
    assert restored.classification_evidence[0]["label"] == "Alzheimer Disease"
    assert restored.authoritative_topics[0]["topic"] == "Causal Learning"
    assert len(restored.references) == 1
    assert restored.references[0].title == "Cited aging mechanism paper"
    assert restored.references[0].doi == "10.1/ref"
    assert restored.references[0].relevance_score == 0.5


def test_pdf_validation_result_defaults_are_explicit():
    result = PdfValidationResult(is_complete=False, status="too_small")

    assert result.is_complete is False
    assert result.status == "too_small"
    assert result.reason == ""
    assert result.page_count is None
    assert result.file_size is None
    assert result.has_abstract is False
    assert result.has_references is False
    assert result.has_paywall_marker is False

