# -*- coding: utf-8 -*-

import json

from refchaser.paper_models import ArticleRecord
from refchaser.reference_extractor import PdfReferenceExtractor, ReferenceExtractionService, run_from_args


REFERENCE_TEXT = """
Introduction
Some body text.

References
1. Smith, A. & Lee, B. Peroxisomal lipid metabolism in aging. Nature Aging 1, 10-20 (2024). https://doi.org/10.1038/s43587-024-00001-1
2. Zhang, C. Biomarkers of mitochondrial dysfunction. Cell Metab. 30, 1-9 (2023). doi:10.1016/j.cmet.2023.01.001

Acknowledgements
Thanks.
"""


def test_extract_reference_section_stops_at_acknowledgements():
    extractor = PdfReferenceExtractor()

    section = extractor.extract_reference_section(REFERENCE_TEXT)

    assert "Peroxisomal lipid metabolism" in section
    assert "Acknowledgements" not in section


def test_split_references_by_numbered_items():
    extractor = PdfReferenceExtractor()
    section = extractor.extract_reference_section(REFERENCE_TEXT)

    refs = extractor.split_references(section)

    assert len(refs) == 2
    assert refs[0].startswith("Smith")
    assert refs[1].startswith("Zhang")


def test_parse_reference_extracts_doi_year_authors_and_title():
    extractor = PdfReferenceExtractor()
    source = ArticleRecord(title="Source paper", doi="10.1/source")

    reference = extractor.parse_reference(
        "Smith, A. & Lee, B. Peroxisomal lipid metabolism in aging. Nature Aging 1, 10-20 (2024). https://doi.org/10.1038/s43587-024-00001-1",
        source,
    )

    assert reference.doi == "10.1038/s43587-024-00001-1"
    assert reference.publish_date == "2024"
    assert reference.journal == "Nature Aging"
    assert reference.source_article_doi == "10.1/source"
    assert "Smith" in reference.authors[0]
    assert "Peroxisomal lipid metabolism" in reference.title


def test_parse_reference_removes_multi_initial_author_prefix():
    extractor = PdfReferenceExtractor()
    source = ArticleRecord(title="Source paper", doi="10.1/source")

    reference = extractor.parse_reference(
        "Goodpaster, B. H., Sparks, L. M. & Smith, S. R. Metabolic flexibility in health and disease. Cell Metab. 25, 1027-1036 (2017).",
        source,
    )

    assert reference.title == "Metabolic flexibility in health and disease"
    assert reference.journal == "Cell Metab"


def test_reference_extraction_service_updates_manifest(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF- fake")
    manifest = tmp_path / "article_manifest.json"
    article = ArticleRecord(
        title="Source paper",
        doi="10.1/source",
        local_pdf_path=pdf,
        download_status="downloaded",
        pdf_status="complete",
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = ReferenceExtractionService(manifest)
    monkeypatch.setattr(service.extractor, "extract_text", lambda path: REFERENCE_TEXT)

    articles = service.run()
    saved = json.loads(manifest.read_text(encoding="utf-8"))

    assert len(articles[0].references) == 2
    assert saved[0]["references"][0]["doi"] == "10.1038/s43587-024-00001-1"


def test_extract_from_article_deduplicates_references_by_doi(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF- fake")
    article = ArticleRecord(
        title="Source paper",
        doi="10.1/source",
        local_pdf_path=pdf,
        pdf_status="complete",
    )
    text = """
References
1. Smith, A. & Lee, B. Peroxisomal lipid metabolism in aging. Nature Aging 1, 10-20 (2024). https://doi.org/10.1038/s43587-024-00001-1
2. Smith, A. & Lee, B. Peroxisomal lipid metabolism in aging. Nature Aging 1, 10-20 (2024). doi:10.1038/s43587-024-00001-1
"""
    extractor = PdfReferenceExtractor()
    monkeypatch.setattr(extractor, "extract_text", lambda path: text)

    references = extractor.extract_from_article(article)

    assert len(references) == 1
    assert references[0].doi == "10.1038/s43587-024-00001-1"


def test_reference_extraction_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "article_manifest.json")
        max_references = 5

    monkeypatch.setattr(ReferenceExtractionService, "run", lambda self: [])

    assert run_from_args(Args()) == 0
