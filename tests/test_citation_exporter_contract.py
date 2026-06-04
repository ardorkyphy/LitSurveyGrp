# -*- coding: utf-8 -*-

import json

import pytest

from litsurveygrp.citation_exporter import (
    ReferenceRelevanceScorer,
    ReferenceRisExporter,
    RisExporter,
    relevance_percent_to_threshold,
    run_from_args,
    validate_max_records,
)
from litsurveygrp.paper_models import ArticleRecord, ReferenceRecord


def test_ris_exporter_default_output_path(tmp_path):
    manifest = tmp_path / "classified_manifest.json"
    exporter = RisExporter(manifest)

    assert exporter.manifest_path == manifest
    assert exporter.output_path == tmp_path / "source_papers.ris"


def test_ris_exporter_custom_output_path(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    output = tmp_path / "custom.ris"
    exporter = RisExporter(manifest, output)

    assert exporter.output_path == output


def test_ris_exporter_formats_article():
    exporter = RisExporter("manifest.json")
    article = ArticleRecord(
        title="Aging paper",
        doi="10.1038/test",
        journal="Nature Aging",
        publish_date="2026/05",
        authors=["Alice", "Bob"],
        abstract="Line one.\nLine two.",
    )

    text = exporter.format_article(article)

    assert "TY  - JOUR" in text
    assert "TI  - Aging paper" in text
    assert "AU  - Alice" in text
    assert "AU  - Bob" in text
    assert "PY  - 2026" in text
    assert "DO  - 10.1038/test" in text
    assert "JF  - Nature Aging" in text
    assert "AB  - Line one. Line two." in text
    assert text.endswith("ER  -\n")


def test_ris_exporter_loads_and_exports_only_records_with_doi(tmp_path):
    manifest = tmp_path / "classified_manifest.json"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF- test")
    articles = [
        ArticleRecord(
            title="Export me",
            doi="10.1/export",
            authors=["Alice"],
            local_pdf_path=pdf,
            download_status="downloaded",
            pdf_status="complete",
        ),
        ArticleRecord(title="Skip missing doi", doi="", local_pdf_path=pdf, download_status="downloaded", pdf_status="complete"),
        ArticleRecord(title="Skip incomplete", doi="10.1/skip", download_status="skipped", pdf_status="not_pdf"),
    ]
    manifest.write_text(json.dumps([a.to_manifest_dict() for a in articles]), encoding="utf-8")
    exporter = RisExporter(manifest)

    loaded = exporter.load_manifest()
    output = exporter.export()
    text = output.read_text(encoding="utf-8")

    assert len(loaded) == 3
    assert exporter.should_export(loaded[0]) is True
    assert exporter.should_export(loaded[1]) is False
    assert exporter.should_export(loaded[2]) is False
    assert "TI  - Export me" in text
    assert "TI  - Skip missing doi" not in text
    assert "TI  - Skip incomplete" not in text


def test_ris_exporter_summary_counts_exported_and_skipped(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF- test")
    articles = [
        ArticleRecord(title="One", doi="10.1/one", local_pdf_path=pdf, download_status="downloaded", pdf_status="complete"),
        ArticleRecord(title="Two", doi="10.1/two", download_status="skipped", pdf_status="not_pdf"),
    ]
    manifest.write_text(json.dumps([a.to_manifest_dict() for a in articles]), encoding="utf-8")
    exporter = RisExporter(manifest)

    summary = exporter.export_summary()

    assert summary["total_records"] == 2
    assert summary["exported_records"] == 1
    assert summary["skipped_records"] == 1


def test_ris_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "classified_manifest.json")
        out = None

    monkeypatch.setattr(RisExporter, "export", lambda self: self.output_path)

    assert run_from_args(Args()) == 0


def test_reference_relevance_scorer_scores_shared_domain_terms():
    source = ArticleRecord(
        title="Peroxisome mechanism in metabolic aging",
        abstract="Peroxisome dysfunction impairs lipid metabolism during aging.",
        subdomain="Mechanism_Research",
    )
    relevant = ReferenceRecord(title="Peroxisomal lipid metabolism and longevity")
    irrelevant = ReferenceRecord(title="Unrelated software engineering methods")
    scorer = ReferenceRelevanceScorer(threshold=0.1)

    scorer.score(source, relevant)
    scorer.score(source, irrelevant)

    assert relevant.relevance_score >= 0.1
    assert "peroxis" in relevant.relevance_reason or "lipid" in relevant.relevance_reason
    assert irrelevant.relevance_score < relevant.relevance_score


def test_reference_relevance_scorer_keeps_domain_references_from_short_titles():
    source = ArticleRecord(
        title="Proteomic signatures of APOE variants and Alzheimer disease",
        abstract="This study analyzes APOE4 and APOE2 effects in Alzheimer disease.",
        subdomain="Neurodegeneration",
    )
    reference = ReferenceRecord(title="APOE and Alzheimer disease: a major gene with semi-dominant inheritance")
    scorer = ReferenceRelevanceScorer(threshold=0.12)

    scorer.score(source, reference)

    assert reference.relevance_score >= 0.12


def test_reference_ris_exporter_exports_relevant_references_only_and_deduplicates(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    source = ArticleRecord(
        title="Peroxisome mechanism in metabolic aging",
        doi="10.1/source",
        abstract="Peroxisome dysfunction impairs lipid metabolism during aging.",
        subdomain="Mechanism_Research",
        references=[
            ReferenceRecord(title="Peroxisomal lipid metabolism and longevity", doi="10.1/ref", authors=["Alice"]),
            ReferenceRecord(title="Peroxisomal lipid metabolism and longevity", doi="10.1/ref", authors=["Alice"]),
            ReferenceRecord(title="Unrelated software engineering methods", doi="10.1/skip"),
        ],
    )
    manifest.write_text(json.dumps([source.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    exporter = ReferenceRisExporter(manifest, relevance_threshold=0.1)

    output = exporter.export()
    text = output.read_text(encoding="utf-8")
    summary = exporter.export_summary()

    assert output.name == "reference_papers.ris"
    assert text.count("TY  - JOUR") == 1
    assert "TI  - Peroxisomal lipid metabolism and longevity" in text
    assert "TI  - Unrelated software engineering methods" not in text
    assert summary["total_references"] == 3
    assert summary["exported_records"] == 1


def test_reference_ris_exporter_limits_records_by_relevance_score(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    source = ArticleRecord(
        title="APOE Alzheimer disease proteomic signatures",
        abstract="APOE and Alzheimer disease proteins.",
        subdomain="Neurodegeneration",
        references=[
            ReferenceRecord(title="APOE Alzheimer disease proteomic signatures"),
            ReferenceRecord(title="Alzheimer amyloid disease"),
            ReferenceRecord(title="APOE unrelated engineering methods"),
        ],
    )
    manifest.write_text(json.dumps([source.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    exporter = ReferenceRisExporter(manifest, relevance_threshold=0.01, max_records=2)

    references = exporter.iter_relevant_references()
    output = exporter.export()
    text = output.read_text(encoding="utf-8")
    summary = exporter.export_summary()

    assert len(references) == 2
    assert references[0].relevance_score >= references[1].relevance_score
    assert text.count("TY  - JOUR") == 2
    assert summary["max_records"] == 2


def test_reference_ris_exporter_can_require_doi(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    source = ArticleRecord(
        title="APOE Alzheimer disease proteomic signatures",
        abstract="APOE and Alzheimer disease proteins.",
        subdomain="Neurodegeneration",
        references=[
            ReferenceRecord(title="APOE Alzheimer disease without doi"),
            ReferenceRecord(title="APOE Alzheimer disease with doi", doi="10.1/ref"),
        ],
    )
    manifest.write_text(json.dumps([source.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    exporter = ReferenceRisExporter(manifest, relevance_threshold=0.01, require_doi=True)

    references = exporter.iter_relevant_references()
    summary = exporter.export_summary()

    assert len(references) == 1
    assert references[0].doi == "10.1/ref"
    assert summary["require_doi"] is True


def test_relevance_percent_to_threshold_converts_percent_to_fraction():
    assert relevance_percent_to_threshold(None) == 0.12
    assert relevance_percent_to_threshold(35) == 0.35


def test_relevance_percent_to_threshold_rejects_out_of_range():
    with pytest.raises(ValueError):
        relevance_percent_to_threshold(-1)
    with pytest.raises(ValueError):
        relevance_percent_to_threshold(101)


def test_validate_max_records_accepts_positive_or_none():
    assert validate_max_records(None) is None
    assert validate_max_records(5) == 5


def test_validate_max_records_rejects_non_positive_values():
    with pytest.raises(ValueError):
        validate_max_records(0)


def test_reference_ris_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "article_manifest.json")
        out = None
        references = True
        max_records = 10
        relevance_percent = 25
        require_doi = True

    captured = {}

    def fake_export(self):
        captured["threshold"] = self.scorer.threshold
        captured["max_records"] = self.max_records
        return self.output_path

    monkeypatch.setattr(ReferenceRisExporter, "export", fake_export)

    assert run_from_args(Args()) == 0
    assert captured["threshold"] == 0.25
    assert captured["max_records"] == 10

