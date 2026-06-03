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
from collections import Counter, defaultdict
from pathlib import Path

try:
    from sklearn.cluster import AgglomerativeClustering
except ImportError:  # pragma: no cover - optional dependency fallback
    AgglomerativeClustering = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional dependency fallback
    SentenceTransformer = None

from refchaser.paper_models import ArticleRecord


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


class ClusteredPaperClassifier:
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
        sentence_model: str | None = None,
    ):
        self.manifest_path = Path(manifest_path)
        self.root_dir = Path(output_dir) if output_dir else self.manifest_path.parent
        self.organize_dir = Path(organize_dir) if organize_dir else self.root_dir
        self.sentence_model = sentence_model
        self.copy_files = copy_files
        self.clean = clean
        self.classifier = ClusteredPaperClassifier(
            embedder=SentenceTransformerEmbedder(sentence_model or "allenai-specter")
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
        sentence_model=getattr(args, "sentence_model", None),
    )
    service.run()
    return 0
