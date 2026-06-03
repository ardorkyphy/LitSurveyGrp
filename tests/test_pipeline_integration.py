# -*- coding: utf-8 -*-

import json

from refchaser.citation_exporter import ReferenceRisExporter
from refchaser.multi_journal_downloader import JournalConfig, MultiJournalDownloadService
from refchaser.paper_classifier import PaperClassificationService
from refchaser.paper_models import ArticleRecord
from refchaser.reference_extractor import ReferenceExtractionService


REFERENCE_TEXT = """
Introduction
This paper studies semantic segmentation and visual representation learning.

References
1. Smith, A. & Lee, B. Semantic segmentation with visual representation learning. International Journal of Computer Vision 1, 10-20 (2024). https://doi.org/10.1007/ref-one
2. Zhang, C. Unrelated clinical biomarkers in aging. Nature Aging 2, 30-40 (2024). https://doi.org/10.1038/ref-two
"""


def test_download_classify_extract_and_export_reference_pipeline(monkeypatch, tmp_path):
    pdf_path = tmp_path / "all_papers" / "paper.pdf"

    service = MultiJournalDownloadService(
        output_dir=tmp_path,
        journals=[JournalConfig("International Journal of Computer Vision", provider="openalex", issn="0920-5691")],
        limit=1,
        per_journal_limit=1,
    )
    service.iter_articles = lambda: iter([
        ArticleRecord(
            title="Semantic segmentation with visual representation learning",
            doi="10.1007/source",
            journal="International Journal of Computer Vision",
            pdf_url="https://example.org/paper.pdf",
            abstract="This paper studies semantic segmentation and visual representation learning.",
        )
    ])

    def fake_download(article):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF- integration")
        article.local_pdf_path = pdf_path
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        return article

    service.downloader.download = fake_download

    downloaded = service.run()
    manifest = tmp_path / "multi_journal_manifest.json"

    assert len(downloaded) == 1
    assert manifest.exists()

    classification = PaperClassificationService(manifest)
    classification.classifier.classify_batch = lambda articles: [
        setattr(article, "subdomain", "Topic_Semantic_Segmentation") or article
        for article in articles
    ]
    classified = classification.run()

    assert classified[0].subdomain
    assert (tmp_path / "classified_manifest.json").exists()
    assert (tmp_path / "basic_stats.json").exists()

    extraction = ReferenceExtractionService(manifest, max_references_per_article=10)
    monkeypatch.setattr(extraction.extractor, "extract_text", lambda path: REFERENCE_TEXT)
    extracted = extraction.run()
    saved = json.loads(manifest.read_text(encoding="utf-8"))

    assert len(extracted[0].references) == 2
    assert saved[0]["references"][0]["doi"] == "10.1007/ref-one"

    ris_path = ReferenceRisExporter(
        manifest,
        relevance_threshold=0.2,
        max_records=10,
        require_doi=True,
    ).export()
    ris_text = ris_path.read_text(encoding="utf-8")

    assert ris_path.name == "reference_papers.ris"
    assert "TY  - JOUR" in ris_text
    assert "DO  - 10.1007/ref-one" in ris_text
