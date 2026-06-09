# -*- coding: utf-8 -*-

from agents.evidence import build_evidence_bundle, chunk_text, selected_text


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([
                1.0 if any(term in lowered for term in ["gap", "objective", "problem"]) else 0.0,
                1.0 if any(term in lowered for term in ["method", "pipeline", "cohort", "dataset", "model"]) else 0.0,
                1.0 if any(term in lowered for term in ["result", "finding", "performance"]) else 0.0,
                1.0 if any(term in lowered for term in ["limitation", "future", "validation"]) else 0.0,
            ])
        return vectors


class FakeRerankerModel:
    def predict(self, pairs):
        return [0.5 for _ in pairs]


def patch_models(monkeypatch):
    monkeypatch.setattr("agents.evidence.load_deployed_embedding_model", lambda: FakeEmbeddingModel())
    monkeypatch.setattr("agents.evidence.load_deployed_reranker_model", lambda: FakeRerankerModel())


def test_evidence_bundle_selects_key_sections_and_terms(monkeypatch):
    patch_models(monkeypatch)
    text = """
Introduction
This paper addresses a major research gap in robust neural decoding.
Methods
We propose a pipeline using a cohort dataset and a machine learning model.
Results
The results demonstrate improved performance across subjects.
Discussion
However, limitations remain and further validation is needed.
"""

    bundle = build_evidence_bundle(
        paper_id="paper_001",
        abstract="We study neural decoding methods.",
        text=text,
        max_chunks=6,
        chunk_chars=500,
    )

    assert bundle["mode"] == "semantic_evidence_chunks"
    assert bundle["selection_method"] == "bge_embedding_reranker"
    assert bundle["total_chunks"] >= 4
    assert bundle["selected_chunks"]
    assert bundle["selected_chunks"][0]["models"]["embedding"] == "BAAI/bge-m3"
    assert "embedding_score" in bundle["selected_chunks"][0]
    assert "rerank_score" in bundle["selected_chunks"][0]
    assert "methods" in bundle["coverage"]["selected_sections"]
    assert "findings" in bundle["coverage"]["selected_reasons"]
    assert "pipeline" in selected_text(bundle)


def test_chunk_text_falls_back_to_body_when_headings_are_absent():
    chunks = chunk_text(
        paper_id="paper_001",
        text="A research problem is evaluated with a method. The result is promising.",
        chunk_chars=300,
    )

    assert chunks
    assert chunks[0].section == "body"
