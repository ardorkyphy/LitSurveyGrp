# -*- coding: utf-8 -*-

import json

from refchaser.paper_classifier import (
    BasicStatsWriter,
    ClusteredPaperClassifier,
    PaperClassificationService,
    PaperFolderOrganizer,
    SentenceTransformerEmbedder,
    run_from_args,
)
from refchaser.paper_models import ArticleRecord


class FakeSpecterEmbedder:
    name = "specter:fake"

    def can_embed(self):
        return True

    def embed(self, texts):
        return [
            [1.0, 0.0],
            [0.95, 0.05],
            [0.0, 1.0],
            [0.05, 0.95],
        ][: len(texts)]


def test_sentence_transformer_embedder_reports_availability():
    assert SentenceTransformerEmbedder().name == "specter:allenai-specter"
    assert SentenceTransformerEmbedder().can_embed() in {True, False}


def test_specter_clustered_classifier_groups_articles_from_embeddings():
    classifier = ClusteredPaperClassifier(embedder=FakeSpecterEmbedder(), max_cluster_count=2)
    articles = [
        ArticleRecord(title="APOE Alzheimer biomarker", abstract="Alzheimer biomarker proteomics."),
        ArticleRecord(title="MRI Alzheimer outcome", abstract="Alzheimer imaging biomarker."),
        ArticleRecord(title="Peroxisome lipid metabolism", abstract="Metabolic organelle lipid function."),
        ArticleRecord(title="Muscle stem cell metabolism", abstract="Stem cell metabolic function."),
    ]

    classified = classifier.classify_batch(articles)

    assert classified[0].subdomain == classified[1].subdomain
    assert classified[2].subdomain == classified[3].subdomain
    assert classified[0].subdomain != classified[2].subdomain
    assert all(article.subdomain.startswith("Topic_") for article in classified)
    assert all("embedding=specter:fake" in article.classification_reason for article in classified)
    assert classified[0].problem_statement == "Alzheimer biomarker proteomics."


def test_specter_clustered_classifier_auto_estimates_cluster_count():
    classifier = ClusteredPaperClassifier(embedder=FakeSpecterEmbedder())

    assert classifier._auto_cluster_count(1) == 1
    assert classifier._auto_cluster_count(10) == 4
    assert classifier._auto_cluster_count(100) == classifier.max_cluster_count


def test_folder_organizer_stores_root_and_mode(tmp_path):
    organizer = PaperFolderOrganizer(tmp_path / "论文", copy_files=False)

    assert organizer.root_dir.name == "论文"
    assert organizer.copy_files is False
    assert organizer.clean is True


def test_folder_organizer_copies_pdf_to_classified_subdomain(tmp_path):
    source = tmp_path / "all_papers" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF- test")
    article = ArticleRecord(title="Paper", local_pdf_path=source, subdomain="Topic_Aging_Biomarker")
    organizer = PaperFolderOrganizer(tmp_path)

    organized = organizer.organize([article])

    target = tmp_path / "classified" / "Topic_Aging_Biomarker" / "paper.pdf"
    assert target.exists()
    assert source.exists()
    assert organized[0].local_pdf_path == source


def test_folder_organizer_cleans_stale_classified_outputs(tmp_path):
    stale = tmp_path / "classified" / "Topic_Old" / "old.pdf"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"%PDF- stale")
    source = tmp_path / "all_papers" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF- current")
    article = ArticleRecord(title="Paper", local_pdf_path=source, subdomain="Topic_New")
    organizer = PaperFolderOrganizer(tmp_path)

    organizer.organize([article])

    assert not stale.exists()
    assert (tmp_path / "classified" / "Topic_New" / "paper.pdf").exists()


def test_basic_stats_writer_counts_and_ranks(tmp_path):
    writer = BasicStatsWriter(tmp_path)
    articles = [
        ArticleRecord(
            title="One",
            subdomain="Topic_A",
            authors=["Alice"],
            institutions=["Institute A"],
            citation_count=5,
        ),
        ArticleRecord(
            title="Two",
            subdomain="Topic_A",
            authors=["Alice", "Bob"],
            institutions=["Institute A", "Institute B"],
            citation_count=3,
        ),
    ]

    stats = writer.build_stats(articles)
    path = writer.write(articles)

    assert stats["subdomain_counts"]["Topic_A"] == 2
    assert stats["author_counts"]["Alice"] == 2
    assert stats["institution_counts"]["Institute A"] == 2
    assert stats["author_citation_ranking"][0] == {"name": "Alice", "citation_count": 8}
    assert path.exists()


def test_classification_service_wires_components(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    service = PaperClassificationService(
        manifest,
        copy_files=False,
        output_dir=tmp_path / "results",
        organize_dir=tmp_path / "papers",
        sentence_model="allenai-specter",
    )

    assert service.manifest_path == manifest
    assert service.root_dir == tmp_path / "results"
    assert service.organize_dir == tmp_path / "papers"
    assert service.copy_files is False
    assert isinstance(service.classifier, ClusteredPaperClassifier)
    assert service.classifier.embedder.name == "specter:allenai-specter"


def test_classification_service_loads_classifies_and_writes_outputs(tmp_path):
    papers_dir = tmp_path / "papers"
    results_dir = tmp_path / "results"
    pdf = papers_dir / "all_papers" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF- test")
    manifest = results_dir / "article_manifest.json"
    results_dir.mkdir()
    article = ArticleRecord(
        title="Compound treatment for aging",
        doi="10.1/test",
        abstract="Aging is a problem. A compound improves lifespan.",
        local_pdf_path=pdf,
        authors=["Alice"],
        institutions=["Institute A"],
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = PaperClassificationService(manifest, output_dir=results_dir, organize_dir=papers_dir)
    service.classifier = ClusteredPaperClassifier(embedder=FakeSpecterEmbedder())

    articles = service.run()

    assert articles[0].subdomain.startswith("Topic_")
    assert (results_dir / "classified_manifest.json").exists()
    assert (results_dir / "basic_stats.json").exists()
    classified_files = list((papers_dir / "classified").rglob("paper.pdf"))
    assert len(classified_files) == 1
    assert classified_files[0].parent.name.startswith("Topic_")


def test_classification_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "article_manifest.json")
        move = False
        out_dir = str(tmp_path / "results")
        organize_dir = str(tmp_path / "papers")
        sentence_model = "allenai-specter"

    monkeypatch.setattr(PaperClassificationService, "run", lambda self: [])

    assert run_from_args(Args()) == 0
