# -*- coding: utf-8 -*-
"""
Paper topic clustering and folder organization.

The production batch classifier builds semantic document embeddings, clusters
those embeddings, and derives topic labels from article text. Rule-based
profiles remain as a fallback utility for environments where clustering is
unavailable.
"""

import json
import math
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

try:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize
except ImportError:  # pragma: no cover - optional dependency fallback
    AgglomerativeClustering = None
    TfidfVectorizer = None
    TruncatedSVD = None
    normalize = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional dependency fallback
    SentenceTransformer = None

from refchaser.paper_models import ArticleRecord


DEFAULT_SUBDOMAIN_RULES = {
    "Drug_Discovery": {
        "description": "Therapeutic targets, interventions, compounds, drug-like mechanisms, and treatment strategies for aging.",
        "strong": ["therapeutic", "treatment", "drug", "compound", "target", "intervention"],
        "weak": ["molecule", "screen", "inhibitor", "agonist", "overexpression", "restoring", "improves", "lifespan"],
        "problem": ["decline", "dysfunction", "pathological", "impairs"],
        "method": ["test", "identify", "show", "restore", "overexpression", "degradation"],
    },
    "Health_Management": {
        "description": "Lifestyle, care delivery, healthspan management, exercise, diet, sleep, behavior, and practical aging health management.",
        "strong": ["healthspan", "lifestyle", "exercise", "diet", "sleep", "care", "management"],
        "weak": ["behavior", "nutrition", "activity", "quality of life", "clinical practice", "prevention"],
        "problem": ["frailty", "risk", "disability", "functional decline"],
        "method": ["program", "trial", "recommendation", "monitoring"],
    },
    "Biomarkers": {
        "description": "Measurement signatures, clocks, biomarkers, omics, and diagnostic/prognostic markers of aging.",
        "strong": ["biomarker", "clock", "signature", "methylation", "omics", "marker"],
        "weak": ["proteomic", "metabolomic", "transcriptomic", "epigenetic", "prediction", "diagnostic"],
        "problem": ["measure", "predict", "detect", "stratify"],
        "method": ["model", "assay", "profile", "derive", "validate"],
    },
    "Mechanism_Research": {
        "description": "Basic biological mechanisms, pathways, organelle biology, senescence, inflammation, metabolism, and cellular aging.",
        "strong": ["mechanism", "pathway", "senescence", "inflammation", "mitochondrial", "cellular", "organelle"],
        "weak": ["peroxisome", "metabolic", "lipid", "bioenergetics", "cascade", "homeostasis", "signaling"],
        "problem": ["collapse", "dysfunction", "decline", "impairs", "inflexibility"],
        "method": ["show", "identify", "causally", "using", "overexpression"],
    },
    "Population_Study": {
        "description": "Cohort, epidemiology, longitudinal, population-scale, and risk association studies.",
        "strong": ["cohort", "epidemiology", "population", "longitudinal", "risk"],
        "weak": ["association", "incidence", "prevalence", "participant", "survey", "database"],
        "problem": ["risk factor", "burden", "mortality"],
        "method": ["follow-up", "regression", "analysis", "estimate"],
    },
    "Review": {
        "description": "Review, perspective, comment, news, and conceptual synthesis articles.",
        "strong": ["review", "perspective", "comment", "overview"],
        "weak": ["summarizes", "synthesis", "discuss", "current understanding"],
        "problem": ["knowledge gap", "field"],
        "method": ["summarize", "review", "discuss"],
    },
}


class RuleBasedPaperClassifier:
    """Assign subdomains with local semantic-profile scoring."""

    def __init__(self, rules: dict[str, list[str]] | None = None):
        self.rules = rules or DEFAULT_SUBDOMAIN_RULES

    def classify(self, article: ArticleRecord) -> ArticleRecord:
        """Fill subdomain, problem_statement, and solution_summary."""
        subdomain, confidence, reason = self.score_subdomains(article)
        article.subdomain = subdomain
        article.classification_confidence = confidence
        article.classification_reason = reason
        article.problem_statement = self.infer_problem_statement(article)
        article.solution_summary = self.infer_solution_summary(article)
        return article

    def infer_subdomain(self, article: ArticleRecord) -> str:
        """Return one subdomain name from the configured rules."""
        return self.score_subdomains(article)[0]

    def score_subdomains(self, article: ArticleRecord) -> tuple[str, float, str]:
        """Score all semantic profiles and return best label, confidence, reason."""
        text_parts = self._text_parts(article)
        if self._is_review_like(article, text_parts):
            score, hits = self._score_profile("Review", text_parts)
            confidence = max(0.75, self._confidence(score, score + 2))
            return "Review", round(confidence, 3), "review-like article type/title; hits: " + ", ".join(hits[:5])

        scored = []
        for subdomain in self.rules:
            if subdomain == "Review":
                continue
            score, hits = self._score_profile(subdomain, text_parts)
            scored.append((score, subdomain, hits))
        scored.sort(reverse=True, key=lambda item: item[0])
        best_score, best_subdomain, best_hits = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0
        if best_score <= 0:
            return "Other", 0.0, "no semantic profile matched"
        confidence = self._confidence(best_score, second_score)
        reason = f"profile={best_subdomain}; score={best_score:.2f}; hits: {', '.join(best_hits[:8])}"
        return best_subdomain, round(confidence, 3), reason

    def infer_problem_statement(self, article: ArticleRecord) -> str:
        """Return a coarse problem statement from title/abstract."""
        sentences = self._sentences(article.abstract)
        if sentences:
            return sentences[0]
        return article.title

    def infer_solution_summary(self, article: ArticleRecord) -> str | None:
        """Return a coarse solution summary, or None for review-like papers."""
        if article.subdomain == "Review" or self._is_review_like(article, self._text_parts(article)):
            return None
        sentences = self._sentences(article.abstract)
        if len(sentences) >= 2:
            return " ".join(sentences[-2:])
        if sentences:
            return sentences[0]
        return None

    def _search_text(self, article: ArticleRecord) -> str:
        return " ".join([article.title, article.abstract, article.article_type]).lower()

    def _text_parts(self, article: ArticleRecord) -> dict[str, str]:
        return {
            "title": article.title.lower(),
            "abstract": article.abstract.lower(),
            "article_type": article.article_type.lower(),
        }

    def _sentences(self, text: str) -> list[str]:
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text or "") if item.strip()]

    def _is_review_like(self, article: ArticleRecord, text_parts: dict[str, str]) -> bool:
        article_type = text_parts["article_type"]
        title = text_parts["title"]
        return any(value in article_type for value in ["review", "perspective", "comment"]) or title.startswith("review")

    def _score_profile(self, subdomain: str, text_parts: dict[str, str]) -> tuple[float, list[str]]:
        profile = self.rules[subdomain]
        score = 0.0
        hits = []
        score += self._score_terms(profile.get("strong", []), text_parts, 4.0, hits, "strong")
        score += self._score_terms(profile.get("weak", []), text_parts, 1.5, hits, "weak")
        score += self._score_terms(profile.get("problem", []), text_parts, 1.0, hits, "problem")
        score += self._score_terms(profile.get("method", []), text_parts, 1.0, hits, "method")
        return score, hits

    def _score_terms(
        self,
        terms: list[str],
        text_parts: dict[str, str],
        base_weight: float,
        hits: list[str],
        group: str,
    ) -> float:
        score = 0.0
        for term in terms:
            term_lower = term.lower()
            term_score = 0.0
            if term_lower in text_parts["title"]:
                term_score += base_weight * 1.8
            if term_lower in text_parts["abstract"]:
                term_score += base_weight
            if term_lower in text_parts["article_type"]:
                term_score += base_weight * 1.2
            if term_score:
                score += term_score
                hits.append(f"{group}:{term}")
        return score

    def _confidence(self, best_score: float, second_score: float) -> float:
        if best_score <= 0:
            return 0.0
        margin = max(best_score - second_score, 0.0)
        return min(0.99, 0.45 + (margin / (best_score + 1.0)) * 0.55)


class SklearnLsaEmbedder:
    """Build local semantic embeddings with TF-IDF followed by LSA/SVD."""

    name = "sklearn_lsa"

    def __init__(self, max_features: int = 3000, ngram_range: tuple[int, int] = (1, 2)):
        self.max_features = max_features
        self.ngram_range = ngram_range

    def can_embed(self) -> bool:
        return TfidfVectorizer is not None and TruncatedSVD is not None and normalize is not None

    def embed(self, texts: list[str]):
        if not self.can_embed():
            raise RuntimeError("scikit-learn LSA embedding dependencies are unavailable")
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=self.ngram_range,
            min_df=1,
            max_features=self.max_features,
        )
        matrix = vectorizer.fit_transform(texts)
        if matrix.shape[1] == 0:
            return matrix.toarray()
        component_count = min(max(2, len(texts) - 1), matrix.shape[1] - 1)
        if component_count < 2:
            return normalize(matrix.toarray())
        reduced = TruncatedSVD(n_components=component_count, random_state=42).fit_transform(matrix)
        return normalize(reduced)


class SentenceTransformerEmbedder:
    """Build scientific-paper embeddings with a sentence-transformers model."""

    name = "sentence_transformer"

    def __init__(self, model_name: str = "allenai-specter"):
        self.model_name = model_name
        self._model = None

    def can_embed(self) -> bool:
        return SentenceTransformer is not None

    def embed(self, texts: list[str]):
        if not self.can_embed():
            raise RuntimeError("sentence-transformers is unavailable")
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True)


def build_topic_embedder(embedding_model: str = "lsa", sentence_model: str | None = None):
    """Return the embedding backend requested by CLI/config."""
    value = (embedding_model or "lsa").lower().strip()
    if value in {"lsa", "sklearn-lsa", "sklearn_lsa"}:
        return SklearnLsaEmbedder()
    if value in {"specter", "sentence-transformer", "sentence_transformer"}:
        model_name = sentence_model or "allenai-specter"
        embedder = SentenceTransformerEmbedder(model_name=model_name)
        embedder.name = f"sentence_transformer:{model_name}"
        if not embedder.can_embed():
            raise RuntimeError(
                "SPECTER requires sentence-transformers. Install it with "
                "`python -m pip install sentence-transformers`."
            )
        return embedder
    raise ValueError(f"unsupported embedding model: {embedding_model}")


class ClusteredPaperClassifier:
    """Batch classifier that derives topic labels from unsupervised clustering."""

    def __init__(
        self,
        base_classifier: RuleBasedPaperClassifier | None = None,
        distance_threshold: float = 0.72,
        min_cluster_size: int = 2,
        auto_label_clusters: bool = True,
        fallback_to_rules: bool = False,
        max_cluster_count: int = 8,
        embedder=None,
    ):
        self.base_classifier = base_classifier or RuleBasedPaperClassifier()
        self.distance_threshold = distance_threshold
        self.min_cluster_size = min_cluster_size
        self.auto_label_clusters = auto_label_clusters
        self.fallback_to_rules = fallback_to_rules
        self.max_cluster_count = max_cluster_count
        self.embedder = embedder or SklearnLsaEmbedder()

    def classify_batch(self, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        """Classify articles using cluster-level labels when enough text exists."""
        classified = list(articles)
        for article in classified:
            article.problem_statement = self.base_classifier.infer_problem_statement(article)
            article.solution_summary = self.base_classifier.infer_solution_summary(article)
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
        merged = ArticleRecord(
            title=" ".join(article.title for article in articles),
            abstract=" ".join(article.abstract for article in articles),
            article_type=" ".join(article.article_type for article in articles),
        )
        return self.base_classifier.infer_subdomain(merged)

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
        if self.fallback_to_rules:
            return [self.base_classifier.classify(article) for article in articles]
        for article in articles:
            self._keyword_classify(article, reason)
        return articles

    def _keyword_classify(self, article: ArticleRecord, reason: str) -> ArticleRecord:
        keywords = self._cluster_keywords([article])
        article.subdomain = self._auto_cluster_label(keywords)
        article.classification_confidence = 0.55 if article.subdomain != "Topic_Other" else 0.0
        article.classification_reason = f"auto_topic_fallback={reason}; keywords: {', '.join(keywords[:8])}"
        return article


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
        authors = Counter()
        institutions = Counter()
        author_citations = defaultdict(int)
        institution_citations = defaultdict(int)
        for article in articles:
            subdomains[article.subdomain or "Other"] += 1
            citations = int(article.citation_count or 0)
            for author in article.authors:
                authors[author] += 1
                author_citations[author] += citations
            for institution in article.institutions:
                institutions[institution] += 1
                institution_citations[institution] += citations
        return {
            "subdomain_counts": dict(subdomains),
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
        embedding_model: str = "lsa",
        sentence_model: str | None = None,
    ):
        self.manifest_path = Path(manifest_path)
        self.root_dir = Path(output_dir) if output_dir else self.manifest_path.parent
        self.organize_dir = Path(organize_dir) if organize_dir else self.root_dir
        self.embedding_model = embedding_model
        self.sentence_model = sentence_model
        self.copy_files = copy_files
        self.clean = clean
        self.classifier = ClusteredPaperClassifier(
            embedder=build_topic_embedder(embedding_model, sentence_model)
        )
        self.organizer = PaperFolderOrganizer(self.organize_dir, copy_files=copy_files, clean=clean)
        self.stats = BasicStatsWriter(self.root_dir)

    def run(self) -> list[ArticleRecord]:
        """Load manifest, classify, organize folders, and write outputs."""
        articles = self.classifier.classify_batch(self.load_manifest())
        articles = self.organizer.organize(articles)
        self.write_classified_manifest(articles)
        self.stats.write(articles)
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
    """CLI adapter for python -m refchaser classify-papers."""
    service = PaperClassificationService(
        Path(args.manifest),
        copy_files=not args.move,
        output_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        organize_dir=Path(args.organize_dir) if getattr(args, "organize_dir", None) else None,
        embedding_model=getattr(args, "embedding_model", "lsa"),
        sentence_model=getattr(args, "sentence_model", None),
    )
    service.run()
    return 0
