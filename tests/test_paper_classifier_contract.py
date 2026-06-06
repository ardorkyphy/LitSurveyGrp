# -*- coding: utf-8 -*-

import json

from litsurveygrp.paper_classifier import (
    AuthoritativePaperClassifier,
    BasicStatsWriter,
    ClusteredPaperClassifier,
    ClassificationEvidence,
    CrossrefSubjectProvider,
    DomainRule,
    LegacyClusteredPaperClassifier,
    OpenAlexTopicProvider,
    PaperClassificationService,
    PaperFolderOrganizer,
    PubMedMeshProvider,
    SentenceTransformerEmbedder,
    run_from_args,
)
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.topic_rules import load_domain_rules


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


def test_legacy_specter_clustered_classifier_groups_articles_from_embeddings():
    classifier = LegacyClusteredPaperClassifier(embedder=FakeSpecterEmbedder(), max_cluster_count=2)
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


class FakeMeshProvider:
    name = "pubmed_mesh"
    taxonomy = "MeSH"

    def classify(self, article):
        return [
            ClassificationEvidence(
                source=self.name,
                taxonomy=self.taxonomy,
                label="Alzheimer Disease",
                domain="Alzheimer Disease",
                confidence=0.95,
            )
        ]


class EmptyProvider:
    name = "empty"
    taxonomy = "empty"

    def classify(self, article):
        return []


class ErrorProvider:
    name = "pubmed_mesh"
    taxonomy = "MeSH"

    def classify(self, article):
        raise RuntimeError("offline")


class CountingErrorProvider:
    name = "unstable"
    taxonomy = "unstable"

    def __init__(self):
        self.calls = 0

    def classify(self, article):
        self.calls += 1
        raise RuntimeError("offline")


def test_authoritative_classifier_uses_external_taxonomy_and_records_source():
    classifier = AuthoritativePaperClassifier(providers=[FakeMeshProvider()])
    article = ArticleRecord(title="APOE Alzheimer biomarker")

    classified = classifier.classify_batch([article])[0]

    assert classified.subdomain == "Alzheimer Disease"
    assert classified.classification_source == "pubmed_mesh"
    assert classified.classification_taxonomy == "MeSH"
    assert classified.classification_source_label == "Alzheimer Disease"
    assert classified.classification_confidence == 0.95
    assert "authoritative_source=pubmed_mesh" in classified.classification_reason
    assert classified.classification_evidence[0]["label"] == "Alzheimer Disease"


def test_authoritative_classifier_uses_openalex_official_topic_path_without_domain_remap():
    classifier = AuthoritativePaperClassifier(providers=[OpenAlexTopicProvider()])
    article = ArticleRecord(
        title="Causal representation learning",
        authoritative_topics=[
            {
                "source": "openalex",
                "taxonomy": "OpenAlex Topics",
                "label": "Computer Science > Artificial Intelligence > Causal Representation Learning",
                "field": "Computer Science",
                "subfield": "Artificial Intelligence",
                "topic": "Causal Representation Learning",
            }
        ],
    )
    classified = classifier.classify_batch([article])[0]

    assert classified.subdomain == "Computer Science > Artificial Intelligence > Causal Representation Learning"
    assert classified.classification_source == "openalex"
    assert classified.classification_taxonomy == "OpenAlex Topics"
    assert classified.classification_evidence[0]["raw"]["field"] == "Computer Science"


def test_authoritative_classifier_falls_back_to_transparent_local_rule():
    classifier = AuthoritativePaperClassifier(providers=[EmptyProvider()])
    article = ArticleRecord(
        title="Causal discovery for time series",
        abstract="The algorithm learns causal graphs from temporal observations.",
    )

    classified = classifier.classify_batch([article])[0]

    assert classified.subdomain.startswith("Topic_")
    assert classified.classification_source == "local_rule"
    assert classified.classification_taxonomy == "local transparent keyword rules"
    assert "causal" in classified.classification_source_label


def test_authoritative_classifier_can_use_explicit_domain_rule_template():
    classifier = AuthoritativePaperClassifier(
        providers=[EmptyProvider()],
        local_rules=[DomainRule("Cellular senescence", ["cellular senescence", "sasp"])],
    )
    article = ArticleRecord(
        title="Cellular senescence drives tissue aging",
        abstract="Senescent cells secrete SASP factors.",
    )

    classified = classifier.classify_batch([article])[0]

    assert classified.subdomain == "Cellular senescence"
    assert classified.classification_source == "local_rule"


def test_domain_rules_can_load_json_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps([
            {"domain": "Causal AI", "terms": ["causal discovery", "causal graph"]},
        ]),
        encoding="utf-8",
    )

    custom = load_domain_rules(path)

    assert custom[0].domain == "Causal AI"
    assert custom[0].terms == ["causal discovery", "causal graph"]


def test_authoritative_classifier_uses_existing_authoritative_topics_without_remote_provider():
    class FailingProvider:
        name = "pubmed_mesh"
        taxonomy = "MeSH"

        def classify(self, article):
            raise AssertionError("remote provider should not be called")

    classifier = AuthoritativePaperClassifier(providers=[FailingProvider()])
    article = ArticleRecord(
        title="Neural decoding with AI",
        authoritative_topics=[
            {
                "source": "openalex",
                "taxonomy": "OpenAlex Topics",
                "label": "Computer Science > Artificial Intelligence > Neural Decoding",
            }
        ],
    )

    classified = classifier.classify_batch([article])[0]

    assert classified.subdomain == "Computer Science > Artificial Intelligence > Neural Decoding"
    assert classified.classification_source == "openalex"


def test_authoritative_classifier_parallel_workers_classify_all_records():
    classifier = AuthoritativePaperClassifier(providers=[FakeMeshProvider()], workers=2)
    articles = [ArticleRecord(title=f"Paper {index}") for index in range(4)]

    classified = classifier.classify_batch(articles)

    assert [article.subdomain for article in classified] == ["Alzheimer Disease"] * 4


def test_authoritative_classifier_preserves_provider_errors_on_fallback():
    classifier = AuthoritativePaperClassifier(providers=[ErrorProvider(), EmptyProvider()])
    article = ArticleRecord(title="Alzheimer disease biomarker")

    classified = classifier.classify_batch([article])[0]

    assert classified.classification_source == "local_rule"
    assert classified.classification_evidence[0]["source"] == "pubmed_mesh"
    assert classified.classification_evidence[0]["label"] == "provider_error:RuntimeError"


def test_authoritative_classifier_provider_can_help_skips_unusable_remote_sources():
    assert CrossrefSubjectProvider().can_help(ArticleRecord(title="Paper without DOI")) is False
    assert PubMedMeshProvider().can_help(ArticleRecord(title="Causal graph optimization")) is False
    assert PubMedMeshProvider().can_help(ArticleRecord(title="Neuroscience biomarker", doi="10.1/test")) is True


def test_authoritative_classifier_disables_provider_after_repeated_failures():
    failing = CountingErrorProvider()
    classifier = AuthoritativePaperClassifier(
        providers=[failing, EmptyProvider()],
        request_interval=0,
        failure_breaker_threshold=2,
    )
    articles = [ArticleRecord(title=f"Paper {index}") for index in range(4)]

    classifier.classify_batch(articles)

    assert failing.calls == 2
    assert "unstable" in classifier._disabled_sources


def test_authoritative_classifier_throttles_repeated_calls_to_same_provider_only():
    now = {"value": 100.0}
    sleeps = []

    def fake_monotonic():
        return now["value"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now["value"] += seconds

    classifier = AuthoritativePaperClassifier(
        providers=[EmptyProvider()],
        request_interval=3.0,
        sleep_func=fake_sleep,
        monotonic_func=fake_monotonic,
    )

    classifier.classify_batch([ArticleRecord(title="Paper 1"), ArticleRecord(title="Paper 2")])

    assert sleeps == [3.0]


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
    assert stats["classification_source_counts"]["unknown"] == 2
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
    service.classifier = AuthoritativePaperClassifier(providers=[EmptyProvider()])

    articles = service.run()

    assert articles[0].subdomain.startswith("Topic_")
    assert articles[0].classification_source == "local_rule"
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

