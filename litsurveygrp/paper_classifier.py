# -*- coding: utf-8 -*-
"""
Paper topic clustering and folder organization.

The production batch classifier builds SPECTER document embeddings, clusters
those embeddings, and derives topic labels from article text.
"""

import json
import math
import re
import shutil
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import requests

try:
    from sklearn.cluster import AgglomerativeClustering
except ImportError:  # pragma: no cover - optional dependency fallback
    AgglomerativeClustering = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional dependency fallback
    SentenceTransformer = None

from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.run_monitor import RunMonitor


AUTHORITATIVE_CONFIDENCE = 0.95
EXTERNAL_CONFIDENCE = 0.82
INFERRED_CONFIDENCE = 0.58
DEFAULT_CLASSIFICATION_FAILURE_BREAKER_THRESHOLD = 10
DEFAULT_CLASSIFICATION_REQUEST_INTERVAL_SECONDS = 0.2


@dataclass
class ClassificationEvidence:
    """One external or local classification signal for an article."""

    source: str
    taxonomy: str
    label: str
    domain: str = ""
    confidence: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "taxonomy": self.taxonomy,
            "label": self.label,
            "domain": self.domain,
            "confidence": self.confidence,
            "raw": dict(self.raw),
        }


@dataclass
class DomainRule:
    """Map authoritative taxonomy labels or transparent local text hits to a survey domain."""

    domain: str
    terms: list[str]

    def match_score(self, text: str) -> int:
        score = 0
        for term in self.terms:
            score += count_term(text, term)
        return score


def count_term(text: str, term: str) -> int:
    term = term.lower()
    if any(char in term for char in " -β") or len(term.split()) > 1:
        return text.count(term)
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def map_label_to_domain(label: str, rules: list[DomainRule] | None = None) -> str:
    text = (label or "").lower()
    scored = [(rule.match_score(text), rule.domain) for rule in (rules or [])]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1] if scored and scored[0][0] > 0 else ""


def local_domain_from_article(article: ArticleRecord, rules: list[DomainRule] | None = None) -> tuple[str, str, float]:
    title = (article.title or "").lower()
    text = " ".join([
        article.title or "",
        article.abstract or "",
        article.article_type or "",
        article.journal or "",
    ]).lower()
    if not rules:
        keywords = local_topic_keywords(text)
        if not keywords:
            return "未分类", "", 0.0
        return "Topic_" + "_".join(word.title() for word in keywords[:3]), ", ".join(keywords[:5]), 0.5
    scored = []
    for rule in rules:
        score = rule.match_score(title) * 4 + rule.match_score(text)
        scored.append((score, rule.domain, rule.terms))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] <= 0:
        return "未分类", "", 0.0
    matched_terms = [term for term in scored[0][2] if count_term(text, term) > 0][:5]
    confidence = min(0.72, INFERRED_CONFIDENCE + 0.02 * min(scored[0][0], 7))
    return scored[0][1], ", ".join(matched_terms), round(confidence, 3)


def local_topic_keywords(text: str, limit: int = 5) -> list[str]:
    tokens = Counter()
    stopwords = {
        "this", "that", "with", "from", "paper", "study", "article", "research",
        "using", "based", "analysis", "method", "methods", "results", "shows",
        "journal", "science", "nature", "human", "humans",
    }
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{3,}", (text or "").lower()):
        if token not in stopwords:
            tokens[token] += 1
    return [token for token, _ in tokens.most_common(limit)]


def looks_biomedical_article(article: ArticleRecord) -> bool:
    text = " ".join([
        article.title or "",
        article.abstract or "",
        article.journal or "",
        article.article_type or "",
        " ".join(topic.get("label", "") for topic in article.authoritative_topics or []),
    ]).lower()
    terms = [
        "medicine", "medical", "clinical", "biomedical", "biology", "neuroscience",
        "brain", "neuro", "disease", "patient", "therapy", "diagnosis", "health",
    ]
    return any(term in text for term in terms)


def openalex_topics_from_work(item: dict) -> list[dict]:
    topics = []
    seen = set()
    for topic in item.get("topics") or []:
        parts = [
            ((topic.get("field") or {}).get("display_name") or "").strip(),
            ((topic.get("subfield") or {}).get("display_name") or "").strip(),
            (topic.get("display_name") or "").strip(),
        ]
        label = " > ".join(part for part in parts if part)
        key = ("topic", label.casefold())
        if label and key not in seen:
            seen.add(key)
            topics.append({
                "source": "openalex",
                "taxonomy": "OpenAlex Topics",
                "label": label,
                "field": parts[0],
                "subfield": parts[1],
                "topic": parts[2],
            })
    for concept in item.get("concepts") or []:
        label = (concept.get("display_name") or "").strip()
        if not label:
            continue
        key = ("concept", label.casefold())
        if key in seen:
            continue
        seen.add(key)
        topics.append({
            "source": "openalex",
            "taxonomy": "OpenAlex Concepts",
            "label": label,
            "level": concept.get("level"),
            "score": concept.get("score"),
        })
    return topics


class PubMedMeshProvider:
    """Resolve PubMed MeSH descriptors through NCBI E-utilities."""

    name = "pubmed_mesh"
    taxonomy = "MeSH"
    BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        return bool(article.doi or article.title) and looks_biomedical_article(article)

    def classify(self, article: ArticleRecord) -> list[ClassificationEvidence]:
        pmid = self._find_pmid(article)
        if not pmid:
            return []
        response = self.session.get(
            f"{self.BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        record = (response.json().get("result") or {}).get(str(pmid), {})
        terms = []
        for item in record.get("meshheadinglist") or []:
            if isinstance(item, str):
                terms.append(item)
            elif isinstance(item, dict):
                terms.append(item.get("name") or item.get("term") or "")
        evidence = []
        for term in terms:
            term = str(term or "").strip()
            if term:
                evidence.append(ClassificationEvidence(
                    source=self.name,
                    taxonomy=self.taxonomy,
                    label=term,
                    domain=term,
                    confidence=AUTHORITATIVE_CONFIDENCE,
                ))
        return evidence

    def _find_pmid(self, article: ArticleRecord) -> str:
        query = ""
        if article.doi:
            query = f"{article.doi}[DOI]"
        elif article.title:
            query = f"{article.title}[Title]"
        if not query:
            return ""
        response = self.session.get(
            f"{self.BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        ids = ((response.json().get("esearchresult") or {}).get("idlist") or [])
        return str(ids[0]) if ids else ""


class OpenAlexTopicProvider:
    """Resolve OpenAlex topics/concepts from DOI or title search."""

    name = "openalex"
    taxonomy = "OpenAlex Topics/Concepts"
    API = "https://api.openalex.org/works"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        return bool(article.authoritative_topics or article.doi or article.title)

    def classify(self, article: ArticleRecord) -> list[ClassificationEvidence]:
        if article.authoritative_topics:
            return self._evidence_from_authoritative_topics(article.authoritative_topics)
        item = self._work(article)
        if not item:
            return []
        article.authoritative_topics = openalex_topics_from_work(item)
        return self._evidence_from_authoritative_topics(article.authoritative_topics)

    def _evidence_from_authoritative_topics(self, topics: list[dict]) -> list[ClassificationEvidence]:
        evidence = []
        for topic in topics:
            if topic.get("source") != self.name:
                continue
            label = str(topic.get("label") or "").strip()
            if not label:
                continue
            confidence = EXTERNAL_CONFIDENCE if topic.get("taxonomy") == "OpenAlex Topics" else 0.76
            evidence.append(ClassificationEvidence(
                source=self.name,
                taxonomy=str(topic.get("taxonomy") or self.taxonomy),
                label=label,
                domain=label,
                confidence=confidence,
                raw=topic,
            ))
        return evidence

    def _work(self, article: ArticleRecord) -> dict:
        if article.doi:
            url = f"{self.API}/doi:{article.doi}"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        if not article.title:
            return {}
        response = self.session.get(
            self.API,
            params={"search": article.title, "per-page": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return ((response.json().get("results") or [{}])[0]) or {}


class CrossrefSubjectProvider:
    """Resolve publisher subject labels from Crossref as a low-priority external source."""

    name = "crossref"
    taxonomy = "Crossref subject"
    API = "https://api.crossref.org/v1/works"

    def __init__(self, session=None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout

    def can_help(self, article: ArticleRecord) -> bool:
        return bool(article.doi)

    def classify(self, article: ArticleRecord) -> list[ClassificationEvidence]:
        if not article.doi:
            return []
        response = self.session.get(f"{self.API}/{article.doi}", timeout=self.timeout)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        item = (response.json().get("message") or {})
        evidence = []
        for label in item.get("subject") or []:
            label = str(label or "").strip()
            if label:
                evidence.append(ClassificationEvidence(
                    source=self.name,
                    taxonomy=self.taxonomy,
                    label=label,
                    domain=label,
                    confidence=0.72,
                ))
        return evidence


class AuthoritativePaperClassifier:
    """Classify articles from authoritative external taxonomies, with transparent local fallback."""

    def __init__(
        self,
        providers: list | None = None,
        timeout: int = 15,
        monitor: RunMonitor | None = None,
        local_rules: list[DomainRule] | None = None,
        workers: int = 1,
        request_interval: float = DEFAULT_CLASSIFICATION_REQUEST_INTERVAL_SECONDS,
        failure_breaker_threshold: int = DEFAULT_CLASSIFICATION_FAILURE_BREAKER_THRESHOLD,
        sleep_func=None,
        monotonic_func=None,
    ):
        self.providers = providers if providers is not None else [
            PubMedMeshProvider(timeout=timeout),
            OpenAlexTopicProvider(timeout=timeout),
            CrossrefSubjectProvider(timeout=timeout),
        ]
        self.monitor = monitor
        self.local_rules = local_rules
        self.workers = max(1, int(workers or 1))
        self.request_interval = max(0.0, float(request_interval))
        self.failure_breaker_threshold = max(0, int(failure_breaker_threshold or 0))
        self.sleep_func = sleep_func or time.sleep
        self.monotonic_func = monotonic_func or time.monotonic
        self._monitor_lock = threading.Lock()
        self._provider_locks: dict[str, threading.Lock] = {}
        self._provider_locks_lock = threading.Lock()
        self._breaker_lock = threading.Lock()
        self._last_request_by_source: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._disabled_sources: set[str] = set()

    def classify_batch(self, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        classified = list(articles)
        if self.workers <= 1 or len(classified) <= 1:
            for index, article in enumerate(classified, start=1):
                self.classify_one(article)
                self._update_monitor(index, len(classified), article)
            return classified

        completed = 0
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [executor.submit(self.classify_one, article) for article in classified]
            for future in as_completed(futures):
                article = future.result()
                completed += 1
                self._update_monitor(completed, len(classified), article)
        return classified

    def classify_one(self, article: ArticleRecord) -> ArticleRecord:
        article.problem_statement = self._infer_problem_statement(article)
        article.solution_summary = self._infer_solution_summary(article)
        return self.classify_article(article)

    def classify_article(self, article: ArticleRecord) -> ArticleRecord:
        external_evidence = self._external_evidence(article)
        valid_evidence = [item for item in external_evidence if item.domain]
        if valid_evidence:
            best = self._best_evidence(valid_evidence)
            self._apply_evidence(article, best, external_evidence)
            return article
        domain, label, confidence = local_domain_from_article(article, self.local_rules)
        if domain != "未分类":
            article.subdomain = domain
            article.classification_confidence = confidence
            article.classification_source = "local_rule"
            article.classification_source_label = label
            article.classification_taxonomy = "local transparent keyword rules"
            article.classification_reason = f"inferred_by=local_rule; matched_terms: {label}"
            article.classification_evidence = [item.to_dict() for item in external_evidence] + [{
                "source": "local_rule",
                "taxonomy": "local transparent keyword rules",
                "label": label,
                "domain": domain,
                "confidence": confidence,
            }]
            return article
        article.subdomain = "未分类"
        article.classification_confidence = 0.0
        article.classification_source = "none"
        article.classification_source_label = ""
        article.classification_taxonomy = ""
        article.classification_reason = "no authoritative taxonomy match and no local rule match"
        article.classification_evidence = [item.to_dict() for item in external_evidence]
        return article

    def _external_evidence(self, article: ArticleRecord) -> list[ClassificationEvidence]:
        all_evidence = []
        if article.authoritative_topics:
            evidence = OpenAlexTopicProvider().classify(article)
            return evidence if any(item.domain for item in evidence) else []
        for provider in self.providers:
            if self.is_provider_disabled(provider):
                continue
            if not self.provider_can_help(provider, article):
                continue
            try:
                self.throttle_provider(provider)
                evidence = provider.classify(article)
            except Exception as exc:
                self.record_provider_failure(provider, exc)
                all_evidence.append(ClassificationEvidence(
                    source=getattr(provider, "name", provider.__class__.__name__),
                    taxonomy=getattr(provider, "taxonomy", ""),
                    label=f"provider_error:{exc.__class__.__name__}",
                    confidence=0.0,
                ))
                continue
            self.record_provider_success(provider)
            all_evidence.extend(evidence)
            if any(item.domain for item in evidence):
                return all_evidence
        return all_evidence

    def provider_name(self, provider) -> str:
        return getattr(provider, "name", provider.__class__.__name__)

    def provider_can_help(self, provider, article: ArticleRecord) -> bool:
        can_help = getattr(provider, "can_help", None)
        if can_help is None:
            return True
        return bool(can_help(article))

    def is_provider_disabled(self, provider) -> bool:
        with self._breaker_lock:
            return self.provider_name(provider) in self._disabled_sources

    def record_provider_success(self, provider) -> None:
        with self._breaker_lock:
            self._consecutive_failures[self.provider_name(provider)] = 0

    def record_provider_failure(self, provider, exc: Exception) -> None:
        if self.failure_breaker_threshold <= 0:
            return
        name = self.provider_name(provider)
        disabled = False
        with self._breaker_lock:
            count = self._consecutive_failures.get(name, 0) + 1
            self._consecutive_failures[name] = count
            if count >= self.failure_breaker_threshold and name not in self._disabled_sources:
                self._disabled_sources.add(name)
                disabled = True
        if disabled and self.monitor:
            self.monitor.add_event(
                "classification_provider_disabled",
                f"{name} disabled after {count} consecutive {exc.__class__.__name__} errors",
            )
            self.monitor.write()

    def throttle_provider(self, provider) -> None:
        if self.request_interval <= 0:
            return
        name = self.provider_name(provider)
        with self._provider_lock(name):
            now = self.monotonic_func()
            last = self._last_request_by_source.get(name)
            if last is not None:
                wait_seconds = self.request_interval - (now - last)
                if wait_seconds > 0:
                    self.sleep_func(wait_seconds)
                    now = self.monotonic_func()
            self._last_request_by_source[name] = now

    def _provider_lock(self, provider_name: str) -> threading.Lock:
        with self._provider_locks_lock:
            if provider_name not in self._provider_locks:
                self._provider_locks[provider_name] = threading.Lock()
            return self._provider_locks[provider_name]

    def _best_evidence(self, evidence: list[ClassificationEvidence]) -> ClassificationEvidence:
        priority = {"pubmed_mesh": 0, "openalex": 1, "crossref": 2}
        taxonomy_priority = {"Mesh": 0, "MeSH": 0, "OpenAlex Topics": 1, "OpenAlex Concepts": 2, "Crossref subject": 3}
        indexed = list(enumerate(evidence))
        return sorted(
            indexed,
            key=lambda item: (
                priority.get(item[1].source, 9),
                taxonomy_priority.get(item[1].taxonomy, 9),
                -item[1].confidence,
                item[0],
            ),
        )[0][1]

    def _apply_evidence(
        self,
        article: ArticleRecord,
        best: ClassificationEvidence,
        evidence: list[ClassificationEvidence],
    ) -> None:
        article.subdomain = best.domain
        article.classification_confidence = best.confidence
        article.classification_source = best.source
        article.classification_source_label = best.label
        article.classification_taxonomy = best.taxonomy
        article.classification_reason = (
            f"authoritative_source={best.source}; taxonomy={best.taxonomy}; label={best.label}"
        )
        article.classification_evidence = [item.to_dict() for item in evidence]

    def _infer_problem_statement(self, article: ArticleRecord) -> str:
        sentences = self._sentences(article.abstract)
        if sentences:
            return sentences[0]
        return article.title

    def _infer_solution_summary(self, article: ArticleRecord) -> str | None:
        sentences = self._sentences(article.abstract)
        if len(sentences) >= 2:
            return " ".join(sentences[-2:])
        if sentences:
            return sentences[0]
        return None

    def _sentences(self, text: str) -> list[str]:
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text or "") if item.strip()]

    def _update_monitor(self, processed: int, total: int, article: ArticleRecord) -> None:
        if self.monitor is None:
            return
        with self._monitor_lock:
            self.monitor.update(
                stage="classify",
                message=f"Classified record {processed} of {total}",
                processed=processed,
                total=total,
                current_item=article.title,
                metrics={
                    "classification_source": article.classification_source or "unknown",
                    "classification_label": article.classification_source_label,
                    "classification_domain": article.subdomain,
                },
            )


class SentenceTransformerEmbedder:
    """Build scientific-paper embeddings with SPECTER."""

    name = "sentence_transformer"

    def __init__(self, model_name: str = "allenai-specter"):
        self.model_name = model_name
        self._model = None
        self.name = f"specter:{model_name}"

    def can_embed(self) -> bool:
        return SentenceTransformer is not None

    def embed(self, texts: list[str]):
        if not self.can_embed():
            raise RuntimeError("sentence-transformers is unavailable")
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True)


class LegacyClusteredPaperClassifier:
    """Batch classifier that derives topic labels from unsupervised clustering."""

    def __init__(
        self,
        min_cluster_size: int = 2,
        auto_label_clusters: bool = True,
        max_cluster_count: int = 8,
        embedder=None,
    ):
        self.min_cluster_size = min_cluster_size
        self.auto_label_clusters = auto_label_clusters
        self.max_cluster_count = max_cluster_count
        self.embedder = embedder or SentenceTransformerEmbedder()

    def classify_batch(self, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        """Classify articles using cluster-level labels when enough text exists."""
        classified = list(articles)
        for article in classified:
            article.problem_statement = self._infer_problem_statement(article)
            article.solution_summary = self._infer_solution_summary(article)
        if len(classified) < self.min_cluster_size or not self._can_cluster():
            return self._fallback_classify(classified, "insufficient records for clustering")
        texts = [self._document_text(article) for article in classified]
        if sum(bool(text.strip()) for text in texts) < self.min_cluster_size:
            return self._fallback_classify(classified, "insufficient article text for clustering")
        try:
            labels = self._cluster_labels(texts)
        except Exception:
            return self._fallback_classify(classified, "clustering failed")
        clusters = defaultdict(list)
        for index, label in enumerate(labels):
            clusters[label].append(index)
        for label, indexes in clusters.items():
            if len(indexes) < self.min_cluster_size:
                for index in indexes:
                    self._keyword_classify(classified[index], f"cluster={label}; singleton topic")
                continue
            cluster_label, confidence, keywords = self._label_cluster([classified[index] for index in indexes])
            for index in indexes:
                article = classified[index]
                article.subdomain = cluster_label
                article.classification_confidence = confidence
                article.classification_reason = (
                    f"auto_cluster={label}; embedding={self.embedder.name}; keywords: {', '.join(keywords[:8])}"
                )
        return classified

    def _can_cluster(self) -> bool:
        return AgglomerativeClustering is not None and self.embedder.can_embed()

    def _cluster_labels(self, texts: list[str]) -> list[int]:
        embeddings = self.embedder.embed(texts)
        if len(embeddings) == 0 or len(embeddings[0]) == 0:
            return [-1 for _ in texts]
        cluster_count = self._auto_cluster_count(len(texts))
        if cluster_count <= 1:
            return [0 for _ in texts]
        clustering = AgglomerativeClustering(
            n_clusters=cluster_count,
            metric="cosine",
            linkage="average",
        )
        return list(clustering.fit_predict(embeddings))

    def _auto_cluster_count(self, article_count: int) -> int:
        if article_count <= 0:
            return 0
        if article_count <= self.min_cluster_size:
            return 1
        estimated = max(2, math.ceil(math.sqrt(article_count)))
        return min(article_count, self.max_cluster_count, estimated)

    def _label_cluster(self, articles: list[ArticleRecord]) -> tuple[str, float, list[str]]:
        keywords = self._cluster_keywords(articles)
        if self.auto_label_clusters:
            label = self._auto_cluster_label(keywords)
            confidence = min(0.95, 0.68 + 0.05 * len(articles))
            return label, round(confidence, 3), keywords
        votes = Counter(article.subdomain for article in articles if article.subdomain and article.subdomain != "Other")
        if votes:
            label = votes.most_common(1)[0][0]
        else:
            label = self._label_from_keywords(articles)
        confidence = min(0.95, 0.68 + 0.05 * len(articles))
        return label, round(confidence, 3), keywords

    def _auto_cluster_label(self, keywords: list[str]) -> str:
        useful = [
            self._normalize_label_token(keyword)
            for keyword in keywords
            if self._normalize_label_token(keyword)
        ]
        deduped = []
        for keyword in useful:
            if keyword not in deduped:
                deduped.append(keyword)
        if not deduped:
            return "Topic_Other"
        return "Topic_" + "_".join(word.title() for word in deduped[:3])

    def _normalize_label_token(self, token: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_").lower()
        stopwords = {
            "paper", "study", "article", "research", "using", "shows", "reveals",
            "science", "nature", "aging", "ageing", "cell", "cells", "human",
            "from", "with", "this", "that", "into", "both", "disease", "journal",
        }
        if len(token) < 4 or token in stopwords:
            return ""
        return token

    def _label_from_keywords(self, articles: list[ArticleRecord]) -> str:
        return self._auto_cluster_label(self._cluster_keywords(articles))

    def _cluster_keywords(self, articles: list[ArticleRecord]) -> list[str]:
        tokens = Counter()
        for article in articles:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{3,}", self._document_text(article).lower()):
                if token not in {"this", "that", "with", "from", "paper", "study", "article"}:
                    tokens[token] += 1
        return [token for token, _ in tokens.most_common(12)]

    def _document_text(self, article: ArticleRecord) -> str:
        return " ".join([
            article.title,
            article.abstract,
            article.article_type,
            article.journal,
        ])

    def _fallback_classify(self, articles: list[ArticleRecord], reason: str) -> list[ArticleRecord]:
        for article in articles:
            self._keyword_classify(article, reason)
        return articles

    def _keyword_classify(self, article: ArticleRecord, reason: str) -> ArticleRecord:
        keywords = self._cluster_keywords([article])
        article.subdomain = self._auto_cluster_label(keywords)
        article.classification_confidence = 0.55 if article.subdomain != "Topic_Other" else 0.0
        article.classification_reason = f"auto_topic_fallback={reason}; keywords: {', '.join(keywords[:8])}"
        return article

    def _infer_problem_statement(self, article: ArticleRecord) -> str:
        sentences = self._sentences(article.abstract)
        if sentences:
            return sentences[0]
        return article.title

    def _infer_solution_summary(self, article: ArticleRecord) -> str | None:
        sentences = self._sentences(article.abstract)
        if len(sentences) >= 2:
            return " ".join(sentences[-2:])
        if sentences:
            return sentences[0]
        return None

    def _sentences(self, text: str) -> list[str]:
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text or "") if item.strip()]


class ClusteredPaperClassifier(AuthoritativePaperClassifier):
    """Compatibility name for the default authoritative-first classifier.

    The previous implementation used unsupervised SPECTER clustering. That code
    remains available as LegacyClusteredPaperClassifier, but the default
    classifier now prefers PubMed MeSH, OpenAlex, and Crossref taxonomy labels.
    """

    def __init__(
        self,
        min_cluster_size: int = 2,
        auto_label_clusters: bool = True,
        max_cluster_count: int = 8,
        embedder=None,
        providers: list | None = None,
        timeout: int = 15,
        monitor: RunMonitor | None = None,
        local_rules: list[DomainRule] | None = None,
        workers: int = 1,
        request_interval: float = DEFAULT_CLASSIFICATION_REQUEST_INTERVAL_SECONDS,
        failure_breaker_threshold: int = DEFAULT_CLASSIFICATION_FAILURE_BREAKER_THRESHOLD,
        sleep_func=None,
        monotonic_func=None,
    ):
        self.min_cluster_size = min_cluster_size
        self.auto_label_clusters = auto_label_clusters
        self.max_cluster_count = max_cluster_count
        self.embedder = embedder
        super().__init__(
            providers=providers,
            timeout=timeout,
            monitor=monitor,
            local_rules=local_rules,
            workers=workers,
            request_interval=request_interval,
            failure_breaker_threshold=failure_breaker_threshold,
            sleep_func=sleep_func,
            monotonic_func=monotonic_func,
        )

    def _auto_cluster_count(self, article_count: int) -> int:
        return LegacyClusteredPaperClassifier(
            min_cluster_size=self.min_cluster_size,
            auto_label_clusters=self.auto_label_clusters,
            max_cluster_count=self.max_cluster_count,
            embedder=self.embedder or SentenceTransformerEmbedder(),
        )._auto_cluster_count(article_count)


class PaperFolderOrganizer:
    """Place PDFs into subdomain folders under classified/."""

    def __init__(self, root_dir: Path, copy_files: bool = True, clean: bool = True):
        self.root_dir = Path(root_dir)
        self.copy_files = copy_files
        self.clean = clean

    def organize(self, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        """Copy or move local PDFs into classified/<subdomain>/."""
        classified_root = self.root_dir / "classified"
        if self.clean and classified_root.exists():
            shutil.rmtree(classified_root)
        classified_root.mkdir(parents=True, exist_ok=True)
        for article in articles:
            if not article.local_pdf_path:
                continue
            source = Path(article.local_pdf_path)
            if not source.exists():
                continue
            subdomain = self._safe_folder_name(article.subdomain or "Other")
            target_dir = classified_root / subdomain
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            if source.resolve() != target.resolve():
                if self.copy_files:
                    shutil.copy2(source, target)
                else:
                    shutil.move(str(source), str(target))
                    article.local_pdf_path = target
        return articles

    def _safe_folder_name(self, value: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip() or "Other")
        return re.sub(r"\s+", "_", value)


class BasicStatsWriter:
    """Write MVP statistics for subdomains, authors, and institutions."""

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)

    def build_stats(self, articles: list[ArticleRecord]) -> dict:
        """Return basic counts and citation rankings."""
        subdomains = Counter()
        classification_sources = Counter()
        authors = Counter()
        institutions = Counter()
        author_citations = defaultdict(int)
        institution_citations = defaultdict(int)
        for article in articles:
            subdomains[article.subdomain or "Other"] += 1
            classification_sources[article.classification_source or "unknown"] += 1
            citations = int(article.citation_count or 0)
            for author in article.authors:
                authors[author] += 1
                author_citations[author] += citations
            for institution in article.institutions:
                institutions[institution] += 1
                institution_citations[institution] += citations
        return {
            "subdomain_counts": dict(subdomains),
            "classification_source_counts": dict(classification_sources),
            "author_counts": dict(authors),
            "institution_counts": dict(institutions),
            "author_citation_ranking": self._ranking(author_citations),
            "institution_citation_ranking": self._ranking(institution_citations),
        }

    def write(self, articles: list[ArticleRecord]) -> Path:
        """Write basic_stats.csv or basic_stats.json."""
        path = self.root_dir / "basic_stats.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.build_stats(articles), handle, ensure_ascii=False, indent=2)
        return path

    def _ranking(self, values: dict[str, int]) -> list[dict]:
        return [
            {"name": name, "citation_count": count}
            for name, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))
        ]


class PaperClassificationService:
    """CLI-level service for classify-papers."""

    def __init__(
        self,
        manifest_path: Path,
        copy_files: bool = True,
        clean: bool = True,
        output_dir: Path | None = None,
        organize_dir: Path | None = None,
        sentence_model: str | None = None,
        domain_rules: str | None = None,
        classification_workers: int = 1,
    ):
        self.manifest_path = Path(manifest_path)
        self.root_dir = Path(output_dir) if output_dir else self.manifest_path.parent
        self.organize_dir = Path(organize_dir) if organize_dir else self.root_dir
        self.sentence_model = sentence_model
        self.domain_rules = domain_rules or ""
        self.classification_workers = max(1, int(classification_workers or 1))
        self.copy_files = copy_files
        self.clean = clean
        self.monitor = RunMonitor(self.root_dir)
        from litsurveygrp.topic_rules import load_domain_rules
        self.classifier = ClusteredPaperClassifier(
            embedder=SentenceTransformerEmbedder(sentence_model or "allenai-specter"),
            monitor=self.monitor,
            local_rules=load_domain_rules(self.domain_rules),
            workers=self.classification_workers,
        )
        self.organizer = PaperFolderOrganizer(self.organize_dir, copy_files=copy_files, clean=clean)
        self.stats = BasicStatsWriter(self.root_dir)

    def run(self) -> list[ArticleRecord]:
        """Load manifest, classify, organize folders, and write outputs."""
        source_articles = self.load_manifest()
        self.monitor.start(
            "Paper classification",
            f"Classifying {len(source_articles)} paper records",
            metrics={"total_records": len(source_articles)},
        )
        articles = self.classifier.classify_batch(source_articles)
        self.monitor.update("organize", "Organizing classified PDFs", processed=len(articles), total=len(articles))
        articles = self.organizer.organize(articles)
        manifest_path = self.write_classified_manifest(articles)
        self.monitor.update("stats", "Writing basic classification statistics", processed=len(articles), total=len(articles))
        self.stats.write(articles)
        self.monitor.finish("completed", f"Classification finished: {manifest_path}")
        return articles

    def load_manifest(self) -> list[ArticleRecord]:
        """Read article_manifest.json."""
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def write_classified_manifest(self, articles: list[ArticleRecord]) -> Path:
        """Write classified_manifest.json."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        path = self.root_dir / "classified_manifest.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return path


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp classify-papers."""
    service = PaperClassificationService(
        Path(args.manifest),
        copy_files=not args.move,
        output_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        organize_dir=Path(args.organize_dir) if getattr(args, "organize_dir", None) else None,
        sentence_model=getattr(args, "sentence_model", None),
        domain_rules=getattr(args, "domain_rules", ""),
        classification_workers=getattr(args, "classification_workers", 1),
    )
    service.run()
    return 0

