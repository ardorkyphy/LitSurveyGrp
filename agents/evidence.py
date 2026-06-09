# -*- coding: utf-8 -*-
"""Local evidence selection for PDF-backed research agents.

The agents should process full extracted paper text, but the LLM prompt should
receive a compact, traceable subset of the text. This module keeps the expensive
semantic step focused while preserving enough local coverage to audit what was
shown to the model.
"""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass, replace


SECTION_PATTERNS = [
    ("abstract", re.compile(r"(?im)^\s*abstract\s*$")),
    ("introduction", re.compile(r"(?im)^\s*(\d+\.?\s*)?introduction\s*$")),
    ("background", re.compile(r"(?im)^\s*(\d+\.?\s*)?background\s*$")),
    ("methods", re.compile(r"(?im)^\s*(\d+\.?\s*)?(methods?|materials and methods|methodology)\s*$")),
    ("results", re.compile(r"(?im)^\s*(\d+\.?\s*)?results\s*$")),
    ("discussion", re.compile(r"(?im)^\s*(\d+\.?\s*)?discussion\s*$")),
    ("conclusion", re.compile(r"(?im)^\s*(\d+\.?\s*)?(conclusions?|concluding remarks)\s*$")),
    ("limitations", re.compile(r"(?im)^\s*(\d+\.?\s*)?limitations?\s*$")),
    ("future_work", re.compile(r"(?im)^\s*(\d+\.?\s*)?(future work|future directions)\s*$")),
]

SECTION_PRIORITY = {
    "abstract": 1.7,
    "introduction": 1.4,
    "background": 1.2,
    "methods": 1.35,
    "results": 1.45,
    "discussion": 1.45,
    "conclusion": 1.55,
    "limitations": 1.55,
    "future_work": 1.45,
    "body": 1.0,
}

QUERY_TERMS = {
    "research_problem": [
        "research problem",
        "challenge",
        "gap",
        "aim",
        "objective",
        "question",
        "need",
        "problem",
        "unresolved",
    ],
    "methods": [
        "method",
        "approach",
        "framework",
        "pipeline",
        "model",
        "algorithm",
        "assay",
        "experiment",
        "cohort",
        "dataset",
    ],
    "findings": [
        "result",
        "finding",
        "show",
        "demonstrate",
        "improve",
        "performance",
        "effect",
        "association",
        "evidence",
    ],
    "limitations": [
        "limitation",
        "future",
        "uncertain",
        "however",
        "remain",
        "further",
        "robust",
        "generaliz",
        "validate",
    ],
}

SEMANTIC_QUERIES = {
    "research_problem": "research problem objective knowledge gap unresolved challenge",
    "methods": "methods data materials cohort experiment algorithm model pipeline",
    "findings": "results findings evidence effect performance outcome association",
    "limitations": "limitations uncertainty future work robustness validation constraints",
}

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"
SELECTION_METHOD = "bge_embedding_reranker"
_EMBEDDING_MODEL_CACHE = {}
_RERANKER_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()
_EMBEDDING_INFER_LOCK = threading.Lock()
_RERANKER_INFER_LOCK = threading.Lock()


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    section: str
    text: str
    char_start: int
    char_end: int
    score: float = 0.0
    reasons: tuple[str, ...] = ()
    lexical_score: float = 0.0
    embedding_score: float = 0.0
    rerank_score: float = 0.0
    semantic_purpose: str = ""
    semantic_query: str = ""

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "section": self.section,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "lexical_score": round(self.lexical_score, 4),
            "embedding_score": round(self.embedding_score, 4),
            "rerank_score": round(self.rerank_score, 4),
            "semantic_purpose": self.semantic_purpose,
            "semantic_query": self.semantic_query,
            "selection_method": SELECTION_METHOD,
            "models": {
                "embedding": EMBEDDING_MODEL_NAME,
                "reranker": RERANKER_MODEL_NAME,
            },
        }


def build_evidence_bundle(
    *,
    paper_id: str,
    abstract: str = "",
    text: str = "",
    max_chunks: int = 12,
    chunk_chars: int = 2200,
) -> dict:
    """Return selected chunks plus coverage metadata for one paper."""
    chunks = chunk_text(paper_id=paper_id, abstract=abstract, text=text, chunk_chars=chunk_chars)
    selected = select_evidence_chunks(chunks, max_chunks=max_chunks)
    coverage = coverage_summary(chunks, selected)
    return {
        "mode": "semantic_evidence_chunks",
        "selection_method": SELECTION_METHOD,
        "models": {
            "embedding": EMBEDDING_MODEL_NAME,
            "reranker": RERANKER_MODEL_NAME,
        },
        "total_chunks": len(chunks),
        "selected_chunks": [chunk.to_dict() for chunk in selected],
        "coverage": coverage,
    }


def chunk_text(*, paper_id: str, abstract: str = "", text: str = "", chunk_chars: int = 2200) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    if abstract.strip():
        chunks.append(EvidenceChunk(
            chunk_id=f"{paper_id}:abstract:001",
            section="abstract",
            text=clean_text(abstract)[:chunk_chars],
            char_start=0,
            char_end=len(abstract),
        ))
    for section, start, end, section_text in section_spans(text or ""):
        chunks.extend(split_section(paper_id, section, section_text, start, chunk_chars))
    return chunks


def section_spans(text: str) -> list[tuple[str, int, int, str]]:
    text = text or ""
    if not text.strip():
        return []
    matches = []
    for section, pattern in SECTION_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), section))
    matches.sort(key=lambda item: item[0])
    deduped = []
    last_start = -1
    for start, end, section in matches:
        if start == last_start:
            continue
        deduped.append((start, end, section))
        last_start = start
    if not deduped:
        return [("body", 0, len(text), text)]
    spans = []
    if deduped[0][0] > 0:
        spans.append(("body", 0, deduped[0][0], text[: deduped[0][0]]))
    for index, (start, heading_end, section) in enumerate(deduped):
        end = deduped[index + 1][0] if index + 1 < len(deduped) else len(text)
        section_text = text[heading_end:end]
        if section_text.strip():
            spans.append((section, heading_end, end, section_text))
    return spans


def split_section(paper_id: str, section: str, text: str, section_start: int, chunk_chars: int) -> list[EvidenceChunk]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    sentences = split_sentences(cleaned)
    chunks = []
    current = []
    current_len = 0
    chunk_index = 1
    approx_offset = section_start
    for sentence in sentences:
        if current and current_len + len(sentence) + 1 > chunk_chars:
            chunk_text_value = " ".join(current).strip()
            chunks.append(EvidenceChunk(
                chunk_id=f"{paper_id}:{section}:{chunk_index:03d}",
                section=section,
                text=chunk_text_value,
                char_start=approx_offset,
                char_end=approx_offset + len(chunk_text_value),
            ))
            approx_offset += len(chunk_text_value)
            current = []
            current_len = 0
            chunk_index += 1
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        chunk_text_value = " ".join(current).strip()
        chunks.append(EvidenceChunk(
            chunk_id=f"{paper_id}:{section}:{chunk_index:03d}",
            section=section,
            text=chunk_text_value,
            char_start=approx_offset,
            char_end=approx_offset + len(chunk_text_value),
        ))
    return chunks


def select_evidence_chunks(chunks: list[EvidenceChunk], max_chunks: int = 12) -> list[EvidenceChunk]:
    if not chunks:
        return []
    scored = semantic_score_chunks(chunks)
    selected_by_purpose: dict[str, EvidenceChunk] = {}
    for purpose in SEMANTIC_QUERIES:
        candidates = [chunk for chunk in scored if chunk.semantic_purpose == purpose or purpose in chunk.reasons]
        if candidates:
            selected_by_purpose[purpose] = max(candidates, key=lambda chunk: chunk.score)
    selected = {chunk.chunk_id: chunk for chunk in selected_by_purpose.values()}
    for section in ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "limitations", "future_work"]:
        candidates = [chunk for chunk in scored if chunk.section == section]
        if candidates and len(selected) < max_chunks:
            best = max(candidates, key=lambda chunk: chunk.score)
            selected.setdefault(best.chunk_id, best)
    for chunk in sorted(scored, key=lambda item: (-item.score, item.chunk_id)):
        if len(selected) >= max_chunks:
            break
        selected.setdefault(chunk.chunk_id, chunk)
    return sorted(selected.values(), key=lambda item: item.chunk_id)


def score_chunk(chunk: EvidenceChunk) -> EvidenceChunk:
    normalized = normalize(chunk.text)
    tokens = normalized.split()
    token_count = max(len(tokens), 1)
    reasons = []
    score = SECTION_PRIORITY.get(chunk.section, 1.0)
    for purpose, terms in QUERY_TERMS.items():
        hits = 0
        for term in terms:
            if normalize(term) in normalized:
                hits += 1
        if hits:
            reasons.append(purpose)
            score += (1.0 + math.log1p(hits)) * 1.2
    score += min(token_count / 250.0, 1.0) * 0.3
    return EvidenceChunk(
        chunk_id=chunk.chunk_id,
        section=chunk.section,
        text=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        score=score,
        reasons=tuple(reasons),
        lexical_score=score,
    )


def semantic_score_chunks(chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
    lexical_chunks = [score_chunk(chunk) for chunk in chunks]
    if not lexical_chunks:
        return []

    embedding_model = load_deployed_embedding_model()
    query_items = list(SEMANTIC_QUERIES.items())
    query_texts = [query for _, query in query_items]
    chunk_texts = [chunk.text for chunk in lexical_chunks]
    with _EMBEDDING_INFER_LOCK:
        vectors = embedding_model.encode(
            [*query_texts, *chunk_texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    vectors = [vector_to_list(vector) for vector in vectors]
    query_vectors = vectors[: len(query_texts)]
    chunk_vectors = vectors[len(query_texts):]

    embedded = []
    for chunk, chunk_vector in zip(lexical_chunks, chunk_vectors):
        best_purpose = ""
        best_query = ""
        best_score = float("-inf")
        for (purpose, query), query_vector in zip(query_items, query_vectors):
            similarity = dot(query_vector, chunk_vector)
            if similarity > best_score:
                best_score = similarity
                best_purpose = purpose
                best_query = query
        reasons = list(chunk.reasons)
        if best_purpose and best_purpose not in reasons:
            reasons.append(best_purpose)
        embedded.append(replace(
            chunk,
            embedding_score=float(best_score),
            semantic_purpose=best_purpose,
            semantic_query=best_query,
            reasons=tuple(reasons),
            score=chunk.lexical_score + float(best_score) * 4.0,
        ))

    reranker = load_deployed_reranker_model()
    with _RERANKER_INFER_LOCK:
        rerank_scores = reranker.predict([(chunk.semantic_query, chunk.text) for chunk in embedded])
    ranked = []
    for chunk, rerank_score in zip(embedded, rerank_scores):
        rerank_score = float(rerank_score)
        ranked.append(replace(
            chunk,
            rerank_score=rerank_score,
            score=chunk.lexical_score + chunk.embedding_score * 4.0 + rerank_score,
        ))
    return ranked


def load_deployed_embedding_model():
    from agents.local_models import default_specs, detect_device, load_embedding_model, model_ready

    spec = default_specs(include_reranker=False)[0]
    if not model_ready(spec.path):
        raise RuntimeError(f"local embedding model is not ready at {spec.path}")
    key = (str(spec.path), detect_device("auto"))
    with _MODEL_CACHE_LOCK:
        if key not in _EMBEDDING_MODEL_CACHE:
            _EMBEDDING_MODEL_CACHE[key] = load_embedding_model(device="auto")
        return _EMBEDDING_MODEL_CACHE[key]


def load_deployed_reranker_model():
    from agents.local_models import default_specs, detect_device, load_reranker_model, model_ready

    spec = next(item for item in default_specs(include_reranker=True) if item.role == "reranker")
    if not model_ready(spec.path):
        raise RuntimeError(f"local reranker model is not ready at {spec.path}")
    key = (str(spec.path), detect_device("auto"))
    with _MODEL_CACHE_LOCK:
        if key not in _RERANKER_MODEL_CACHE:
            _RERANKER_MODEL_CACHE[key] = load_reranker_model(device="auto")
        return _RERANKER_MODEL_CACHE[key]


def vector_to_list(vector) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def coverage_summary(chunks: list[EvidenceChunk], selected: list[EvidenceChunk]) -> dict:
    selected_sections = sorted({chunk.section for chunk in selected})
    available_sections = sorted({chunk.section for chunk in chunks})
    selected_reasons = sorted({reason for chunk in selected for reason in chunk.reasons})
    missing_reasons = [purpose for purpose in QUERY_TERMS if purpose not in selected_reasons]
    high_value_sections = [
        section for section in ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "limitations", "future_work"]
        if section in available_sections and section not in selected_sections
    ]
    return {
        "available_sections": available_sections,
        "selected_sections": selected_sections,
        "selected_reasons": selected_reasons,
        "missing_reasons": missing_reasons,
        "unselected_high_value_sections": high_value_sections,
        "coverage_status": "low" if missing_reasons or len(selected) < min(4, len(chunks)) else "ok",
    }


def selected_text(bundle: dict) -> str:
    return "\n".join(chunk.get("text", "") for chunk in bundle.get("selected_chunks") or [])


def clean_text(text: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", text or "")
    return [part.strip() for part in parts if part.strip()]


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()
