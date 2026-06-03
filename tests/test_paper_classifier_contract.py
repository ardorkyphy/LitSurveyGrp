# -*- coding: utf-8 -*-

import json

from refchaser.paper_classifier import (
    BasicStatsWriter,
    ClusteredPaperClassifier,
    DEFAULT_SUBDOMAIN_RULES,
    PaperClassificationService,
    PaperFolderOrganizer,
    RuleBasedPaperClassifier,
    run_from_args,
)
from refchaser.paper_models import ArticleRecord


def test_default_subdomain_rules_cover_mvp_categories():
    expected = {
        "Drug_Discovery",
        "Health_Management",
        "Biomarkers",
        "Mechanism_Research",
        "Population_Study",
        "Review",
    }

    assert expected.issubset(DEFAULT_SUBDOMAIN_RULES)
    assert all(DEFAULT_SUBDOMAIN_RULES[name]["description"] for name in expected)
    assert all(DEFAULT_SUBDOMAIN_RULES[name]["strong"] for name in expected)


def test_classifier_uses_default_rules():
    classifier = RuleBasedPaperClassifier()

    assert classifier.rules is DEFAULT_SUBDOMAIN_RULES


def test_classifier_assigns_subdomain_problem_and_solution():
    classifier = RuleBasedPaperClassifier()
    article = ArticleRecord(
        title="A therapeutic compound for aging",
        abstract="Aging causes metabolic decline. Here we test a compound that improves function.",
        article_type="Article",
    )

    classified = classifier.classify(article)

    assert classified.subdomain == "Drug_Discovery"
    assert classified.classification_confidence > 0
    assert "profile=Drug_Discovery" in classified.classification_reason
    assert classified.problem_statement == "Aging causes metabolic decline."
    assert classified.solution_summary == "Aging causes metabolic decline. Here we test a compound that improves function."


def test_clustered_classifier_groups_low_confidence_related_articles():
    classifier = ClusteredPaperClassifier(distance_threshold=0.8)
    articles = [
        ArticleRecord(
            title="Single-cell atlas maps tumor immune microenvironment",
            abstract="Single-cell transcriptomics maps tumor immune niches and cellular states.",
        ),
        ArticleRecord(
            title="Spatial atlas reveals immune cells in tumors",
            abstract="Spatial transcriptomics identifies tumor immune niches and cell states.",
        ),
        ArticleRecord(
            title="Therapeutic compound improves lifespan",
            abstract="A drug treatment improves lifespan in an aging model.",
        ),
    ]

    classified = classifier.classify_batch(articles)

    assert classified[0].subdomain == classified[1].subdomain
    assert classified[0].subdomain.startswith("Topic_")
    assert "cluster=" in classified[0].classification_reason or "cluster=" in classified[1].classification_reason


def test_classifier_sets_review_solution_to_none():
    classifier = RuleBasedPaperClassifier()
    article = ArticleRecord(
        title="A review of aging clocks",
        abstract="This review summarizes biomarkers.",
        article_type="Review",
    )

    classified = classifier.classify(article)

    assert classified.subdomain == "Review"
    assert classified.classification_confidence >= 0.75
    assert classified.solution_summary is None


def test_semantic_classifier_prefers_mechanism_for_organelle_metabolic_biology():
    classifier = RuleBasedPaperClassifier()
    article = ArticleRecord(
        title="Peroxisomes orchestrate metabolic flexibility and longevity via an interorganelle cascade",
        abstract=(
            "Aging impairs coordinated organelle dynamics essential for lipid metabolism. "
            "Loss of peroxisomal import causes lipid droplet expansion and mitochondrial bioenergetics dysfunction. "
            "Restoring peroxisomal activity reinstates metabolic resilience during aging."
        ),
        article_type="Article",
    )

    classified = classifier.classify(article)

    assert classified.subdomain == "Mechanism_Research"
    assert "organelle" in classified.classification_reason or "peroxisome" in classified.classification_reason


def test_folder_organizer_stores_root_and_mode(tmp_path):
    organizer = PaperFolderOrganizer(tmp_path / "论文", copy_files=False)

    assert organizer.root_dir.name == "论文"
    assert organizer.copy_files is False
    assert organizer.clean is True


def test_folder_organizer_copies_pdf_to_classified_subdomain(tmp_path):
    source = tmp_path / "all_papers" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF- test")
    article = ArticleRecord(title="Paper", local_pdf_path=source, subdomain="Drug_Discovery")
    organizer = PaperFolderOrganizer(tmp_path)

    organized = organizer.organize([article])

    target = tmp_path / "classified" / "Drug_Discovery" / "paper.pdf"
    assert target.exists()
    assert source.exists()
    assert organized[0].local_pdf_path == source


def test_folder_organizer_cleans_stale_classified_outputs(tmp_path):
    stale = tmp_path / "classified" / "Drug_Discovery" / "old.pdf"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"%PDF- stale")
    source = tmp_path / "all_papers" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF- current")
    article = ArticleRecord(title="Paper", local_pdf_path=source, subdomain="Mechanism_Research")
    organizer = PaperFolderOrganizer(tmp_path)

    organizer.organize([article])

    assert not stale.exists()
    assert (tmp_path / "classified" / "Mechanism_Research" / "paper.pdf").exists()


def test_basic_stats_writer_stores_root(tmp_path):
    writer = BasicStatsWriter(tmp_path)

    assert writer.root_dir == tmp_path


def test_basic_stats_writer_counts_and_ranks(tmp_path):
    writer = BasicStatsWriter(tmp_path)
    articles = [
        ArticleRecord(
            title="One",
            subdomain="Drug_Discovery",
            authors=["Alice"],
            institutions=["Institute A"],
            citation_count=5,
        ),
        ArticleRecord(
            title="Two",
            subdomain="Drug_Discovery",
            authors=["Alice", "Bob"],
            institutions=["Institute A", "Institute B"],
            citation_count=3,
        ),
    ]

    stats = writer.build_stats(articles)
    path = writer.write(articles)

    assert stats["subdomain_counts"]["Drug_Discovery"] == 2
    assert stats["author_counts"]["Alice"] == 2
    assert stats["institution_counts"]["Institute A"] == 2
    assert stats["author_citation_ranking"][0] == {"name": "Alice", "citation_count": 8}
    assert path.exists()


def test_classification_service_wires_components(tmp_path):
    manifest = tmp_path / "article_manifest.json"
    service = PaperClassificationService(manifest, copy_files=False)

    assert service.manifest_path == manifest
    assert service.root_dir == tmp_path
    assert service.copy_files is False
    assert service.clean is True
    assert isinstance(service.classifier, ClusteredPaperClassifier)
    assert isinstance(service.organizer, PaperFolderOrganizer)
    assert isinstance(service.stats, BasicStatsWriter)


def test_classification_service_loads_classifies_and_writes_outputs(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF- test")
    manifest = tmp_path / "article_manifest.json"
    article = ArticleRecord(
        title="Compound treatment for aging",
        doi="10.1/test",
        abstract="Aging is a problem. A compound improves lifespan.",
        local_pdf_path=pdf,
        authors=["Alice"],
        institutions=["Institute A"],
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()], ensure_ascii=False), encoding="utf-8")
    service = PaperClassificationService(manifest)

    articles = service.run()

    assert articles[0].subdomain == "Drug_Discovery"
    assert (tmp_path / "classified_manifest.json").exists()
    assert (tmp_path / "basic_stats.json").exists()
    assert (tmp_path / "classified" / "Drug_Discovery" / "paper.pdf").exists()


def test_classification_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "article_manifest.json")
        move = False

    monkeypatch.setattr(PaperClassificationService, "run", lambda self: [])

    assert run_from_args(Args()) == 0
