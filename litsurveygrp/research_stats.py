# -*- coding: utf-8 -*-
"""Research-oriented statistics for enriched/classified paper manifests."""

import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from litsurveygrp.journal_tiers import JournalTierScorer
from litsurveygrp.paper_models import ArticleRecord


class ResearchStatsWriter:
    """Write research statistics that are useful for literature surveys."""

    def __init__(self, manifest_path: Path, out_dir: Path | None = None, top_n: int = 20):
        self.manifest_path = Path(manifest_path)
        self.out_dir = Path(out_dir) if out_dir else self.manifest_path.parent / "stats"
        self.top_n = top_n
        self.journal_scorer = JournalTierScorer()

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def write(self, articles: list[ArticleRecord] | None = None) -> dict[str, Path]:
        articles = articles if articles is not None else self.load_manifest()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "summary": self.out_dir / "summary.json",
            "research_profile": self.out_dir / "research_profile.json",
            "subdomains": self.out_dir / "subdomain_stats.csv",
            "classification_sources": self.out_dir / "classification_source_stats.csv",
            "topic_profiles": self.out_dir / "topic_profiles.csv",
            "years": self.out_dir / "year_trend.csv",
            "authors": self.out_dir / "author_stats.csv",
            "institutions": self.out_dir / "institution_stats.csv",
            "teams": self.out_dir / "team_stats.csv",
            "top_papers": self.out_dir / "top_papers.csv",
            "paper_recommendations": self.out_dir / "paper_recommendations.csv",
            "article_types": self.out_dir / "article_type_stats.csv",
            "journals": self.out_dir / "journal_stats.csv",
            "subdomain_years": self.out_dir / "subdomain_year_trend.csv",
            "citation_buckets": self.out_dir / "citation_bucket_stats.csv",
            "collaboration": self.out_dir / "collaboration_stats.csv",
            "reference_insights": self.out_dir / "reference_insights.csv",
        }
        self._write_json(outputs["summary"], self.summary(articles))
        self._write_json(outputs["research_profile"], self.research_profile(articles))
        self._write_rows(
            outputs["subdomains"],
            self.subdomain_stats(articles),
            [
                "subdomain", "paper_count", "citation_count", "pubmed_mesh_count",
                "openalex_count", "crossref_count", "local_rule_count", "unclassified_count",
            ],
        )
        self._write_rows(
            outputs["classification_sources"],
            self.classification_source_stats(articles),
            ["classification_source", "paper_count", "citation_count"],
        )
        self._write_rows(
            outputs["topic_profiles"],
            self.topic_profiles(articles),
            [
                "subdomain", "paper_count", "citation_count", "average_citations",
                "representative_keywords", "representative_papers", "top_cited_papers",
                "year_span", "trend",
            ],
        )
        self._write_rows(outputs["years"], self.year_trend(articles), ["year", "paper_count", "citation_count"])
        self._write_rows(outputs["authors"], self.author_stats(articles), ["author", "paper_count", "citation_count"])
        self._write_rows(outputs["institutions"], self.institution_stats(articles), ["institution", "paper_count", "citation_count"])
        self._write_rows(outputs["teams"], self.team_stats(articles), ["team", "paper_count", "citation_count"])
        self._write_rows(
            outputs["top_papers"],
            self.top_papers(articles),
            ["title", "doi", "journal", "year", "subdomain", "article_type", "citation_count", "citation_source"],
        )
        self._write_rows(
            outputs["paper_recommendations"],
            self.paper_recommendations(articles),
            [
                "rank", "recommendation_type", "title", "doi", "journal", "journal_tier",
                "year", "subdomain", "article_type", "citation_count", "research_value_score",
                "reason",
            ],
        )
        self._write_rows(outputs["article_types"], self.article_type_stats(articles), ["article_type", "paper_count", "citation_count"])
        self._write_rows(outputs["journals"], self.journal_stats(articles), ["journal", "paper_count", "citation_count"])
        self._write_rows(outputs["subdomain_years"], self.subdomain_year_trend(articles), ["year", "subdomain", "paper_count", "citation_count"])
        self._write_rows(outputs["citation_buckets"], self.citation_bucket_stats(articles), ["citation_bucket", "paper_count", "citation_count"])
        self._write_rows(outputs["collaboration"], self.collaboration_stats(articles), ["collaboration_type", "paper_count", "citation_count"])
        self._write_rows(
            outputs["reference_insights"],
            self.reference_insights(articles),
            [
                "title", "doi", "journal", "year", "citation_count", "source_article_count",
                "relevance_score", "value_score", "journal_tier", "cited_by_source_papers",
            ],
        )
        return outputs

    def summary(self, articles: list[ArticleRecord]) -> dict:
        years = [year for year in [extract_year(article.publish_date) for article in articles] if year]
        citations = [int(article.citation_count or 0) for article in articles]
        complete_pdfs = sum(bool(article.pdf_status == "complete" and article.local_pdf_path) for article in articles)
        return {
            "total_papers": len(articles),
            "year_min": min(years) if years else "",
            "year_max": max(years) if years else "",
            "unique_authors": len({author for article in articles for author in article.authors}),
            "unique_institutions": len({institution for article in articles for institution in article.institutions}),
            "total_citations": sum(citations),
            "average_citations": round(sum(citations) / len(articles), 2) if articles else 0.0,
            "median_citations": median(citations),
            "open_fulltext_coverage": round(complete_pdfs / len(articles), 3) if articles else 0.0,
            "review_papers": sum(is_review_article(article) for article in articles),
            "research_papers": sum(is_research_article(article) for article in articles),
            "reference_pool_size": len(self.reference_insights(articles)),
            "top_subdomains": top_rows_with_other(self.subdomain_stats(articles), self.top_n, "subdomain"),
            "top_authors_by_citations": self.author_stats(articles)[: self.top_n],
            "top_institutions_by_citations": self.institution_stats(articles)[: self.top_n],
            "top_journals_by_citations": self.journal_stats(articles)[: self.top_n],
            "classification_sources": self.classification_source_stats(articles),
        }

    def research_profile(self, articles: list[ArticleRecord]) -> dict:
        """Build a compact research-decision profile for dashboard consumers."""
        recommendations = self.paper_recommendations(articles)
        return {
            "overview": self.summary(articles),
            "topic_profiles": self.topic_profiles(articles)[: self.top_n],
            "year_trend": self.year_trend(articles),
            "growing_topics": self.growing_topics(articles)[: self.top_n],
            "classic_papers": [row for row in recommendations if row["recommendation_type"] == "classic"][: self.top_n],
            "recent_high_potential_papers": [
                row for row in recommendations if row["recommendation_type"] == "recent_high_potential"
            ][: self.top_n],
            "review_entry_points": [row for row in recommendations if row["recommendation_type"] == "review_entry"][: self.top_n],
            "core_references": self.reference_insights(articles)[: self.top_n],
        }

    def subdomain_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        rows = self._group_counts(articles, lambda article: [article.subdomain or "Other"], "subdomain")
        source_counts = defaultdict(Counter)
        for article in articles:
            subdomain = article.subdomain or "Other"
            source = article.classification_source or "unknown"
            source_counts[subdomain][source] += 1
        for row in rows:
            counts = source_counts[row["subdomain"]]
            row["pubmed_mesh_count"] = counts["pubmed_mesh"]
            row["openalex_count"] = counts["openalex"]
            row["crossref_count"] = counts["crossref"]
            row["local_rule_count"] = counts["local_rule"]
            row["unclassified_count"] = counts["none"] + counts["unknown"]
        return rows

    def classification_source_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(
            articles,
            lambda article: [article.classification_source or "unknown"],
            "classification_source",
        )

    def topic_profiles(self, articles: list[ArticleRecord]) -> list[dict]:
        groups = defaultdict(list)
        for article in articles:
            groups[article.subdomain or "Other"].append(article)
        rows = []
        for subdomain, group in groups.items():
            citations = [int(article.citation_count or 0) for article in group]
            years = [extract_year(article.publish_date) for article in group if extract_year(article.publish_date)]
            sorted_by_citations = sorted(group, key=lambda article: (-(article.citation_count or 0), article.title.lower()))
            rows.append({
                "subdomain": subdomain,
                "paper_count": len(group),
                "citation_count": sum(citations),
                "average_citations": round(sum(citations) / len(group), 2) if group else 0.0,
                "representative_keywords": "; ".join(topic_keywords(subdomain, group, limit=8)),
                "representative_papers": " | ".join(article.title for article in group[:3]),
                "top_cited_papers": " | ".join(article.title for article in sorted_by_citations[:3]),
                "year_span": f"{min(years)}-{max(years)}" if years else "Unknown",
                "trend": topic_trend(group),
            })
        return sorted(rows, key=lambda row: (-row["paper_count"], -row["citation_count"], row["subdomain"].lower()))

    def year_trend(self, articles: list[ArticleRecord]) -> list[dict]:
        rows = self._group_counts(articles, lambda article: [extract_year(article.publish_date) or "Unknown"], "year")
        return sorted(rows, key=lambda row: (row["year"] == "Unknown", str(row["year"])))

    def author_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: article.authors, "author")[: self.top_n]

    def institution_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: article.institutions, "institution")[: self.top_n]

    def team_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: [team_label(article)], "team")[: self.top_n]

    def article_type_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: [article.article_type or "Unknown"], "article_type")

    def journal_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: [article.journal or "Unknown"], "journal")[: self.top_n]

    def subdomain_year_trend(self, articles: list[ArticleRecord]) -> list[dict]:
        counts = Counter()
        citations = defaultdict(int)
        for article in articles:
            key = (extract_year(article.publish_date) or "Unknown", article.subdomain or "Other")
            counts[key] += 1
            citations[key] += int(article.citation_count or 0)
        rows = [
            {
                "year": year,
                "subdomain": subdomain,
                "paper_count": counts[(year, subdomain)],
                "citation_count": citations[(year, subdomain)],
            }
            for year, subdomain in counts
        ]
        return sorted(rows, key=lambda row: (row["year"] == "Unknown", str(row["year"]), row["subdomain"].lower()))

    def growing_topics(self, articles: list[ArticleRecord]) -> list[dict]:
        rows = []
        for row in self.topic_profiles(articles):
            if row["trend"] in {"rising", "new"}:
                rows.append(row)
        return sorted(rows, key=lambda row: (row["trend"] != "rising", -row["paper_count"], row["subdomain"].lower()))

    def citation_bucket_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        order = ["0", "1-9", "10-49", "50-99", "100+"]
        rows_by_bucket = {bucket: {"citation_bucket": bucket, "paper_count": 0, "citation_count": 0} for bucket in order}
        for article in articles:
            citations = int(article.citation_count or 0)
            bucket = citation_bucket(citations)
            rows_by_bucket[bucket]["paper_count"] += 1
            rows_by_bucket[bucket]["citation_count"] += citations
        return [rows_by_bucket[bucket] for bucket in order if rows_by_bucket[bucket]["paper_count"]]

    def collaboration_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: [collaboration_type(article)], "collaboration_type")

    def top_papers(self, articles: list[ArticleRecord]) -> list[dict]:
        ranked = sorted(
            articles,
            key=lambda article: (-(article.citation_count or 0), (article.title or "").lower()),
        )
        rows = []
        for article in ranked[: self.top_n]:
            rows.append({
                "title": article.title,
                "doi": article.doi,
                "journal": article.journal,
                "year": extract_year(article.publish_date) or "",
                "subdomain": article.subdomain or "Other",
                "article_type": article.article_type or "Unknown",
                "citation_count": int(article.citation_count or 0),
                "citation_source": article.citation_source,
            })
        return rows

    def paper_recommendations(self, articles: list[ArticleRecord]) -> list[dict]:
        rows = []
        max_citations = max([int(article.citation_count or 0) for article in articles] or [0])
        for article in articles:
            value_score, reason, tier = self.paper_value(article, max_citations)
            rows.append({
                "rank": 0,
                "recommendation_type": recommendation_type(article),
                "title": article.title,
                "doi": article.doi,
                "journal": article.journal,
                "journal_tier": tier,
                "year": extract_year(article.publish_date) or "",
                "subdomain": article.subdomain or "Other",
                "article_type": article.article_type or "Unknown",
                "citation_count": int(article.citation_count or 0),
                "research_value_score": value_score,
                "reason": reason,
            })
        rows = sorted(rows, key=lambda row: (-row["research_value_score"], -row["citation_count"], row["title"].lower()))
        for index, row in enumerate(rows[: self.top_n], start=1):
            row["rank"] = index
        return rows[: self.top_n]

    def paper_value(self, article: ArticleRecord, max_citations: int) -> tuple[float, str, str]:
        tier, tier_score = self.journal_scorer.score(article.journal)
        citation_score = citation_score_from_max(article.citation_count or 0, max_citations)
        recency_value = recency_score(article.publish_date)
        review_score = 0.75 if is_review_article(article) else 0.45
        confidence_score = max(0.0, min(1.0, article.classification_confidence or 0.0))
        metadata_score = metadata_completeness(article)
        value = (
            0.30 * citation_score
            + 0.20 * tier_score
            + 0.18 * recency_value
            + 0.12 * review_score
            + 0.10 * confidence_score
            + 0.10 * metadata_score
        )
        reason = (
            f"citations={citation_score:.3f}; journal={tier}:{tier_score:.3f}; "
            f"recency={recency_value:.3f}; review_entry={review_score:.3f}; metadata={metadata_score:.3f}"
        )
        return round(min(1.0, value), 3), reason, tier

    def reference_insights(self, articles: list[ArticleRecord]) -> list[dict]:
        references = {}
        for article in articles:
            for reference in article.references:
                key = reference.doi.casefold().strip() if reference.doi else reference.title.casefold().strip()
                if not key:
                    continue
                current = references.get(key)
                if current is None:
                    references[key] = reference
                else:
                    current.source_article_count = max(current.source_article_count, reference.source_article_count)
                    current.citation_count = max(int(current.citation_count or 0), int(reference.citation_count or 0))
                    current.relevance_score = max(current.relevance_score, reference.relevance_score)
                    current.value_score = max(current.value_score, reference.value_score)
                    current.source_article_titles = dedupe(current.source_article_titles + reference.source_article_titles)
        rows = []
        for reference in references.values():
            source_titles = reference.source_article_titles or ([reference.source_article_title] if reference.source_article_title else [])
            rows.append({
                "title": reference.title,
                "doi": reference.doi,
                "journal": reference.journal,
                "year": extract_year(reference.publish_date) or "",
                "citation_count": int(reference.citation_count or 0),
                "source_article_count": int(reference.source_article_count or len(source_titles) or 1),
                "relevance_score": round(reference.relevance_score, 3),
                "value_score": round(reference.value_score, 3),
                "journal_tier": reference.journal_tier,
                "cited_by_source_papers": " | ".join(source_titles[:5]),
            })
        return sorted(
            rows,
            key=lambda row: (
                -float(row["value_score"]),
                -float(row["relevance_score"]),
                -int(row["source_article_count"]),
                -int(row["citation_count"]),
                row["title"].lower(),
            ),
        )[: self.top_n]

    def _group_counts(self, articles: list[ArticleRecord], key_func, key_name: str) -> list[dict]:
        counts = Counter()
        citations = defaultdict(int)
        for article in articles:
            keys = [key for key in key_func(article) if key]
            if not keys:
                continue
            for key in dedupe(keys):
                counts[key] += 1
                citations[key] += int(article.citation_count or 0)
        rows = [
            {key_name: key, "paper_count": counts[key], "citation_count": citations[key]}
            for key in counts
        ]
        return sorted(rows, key=lambda row: (-row["citation_count"], -row["paper_count"], str(row[key_name]).lower()))

    def _write_json(self, path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _write_rows(self, path: Path, rows: list[dict], fields: list[str]) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})


def extract_year(value: str) -> str:
    match = re.search(r"(19|20)\d{2}", value or "")
    return match.group(0) if match else ""


def team_label(article: ArticleRecord) -> str:
    if article.institutions:
        return article.institutions[0]
    if len(article.authors) >= 2:
        return f"{article.authors[0]} + {article.authors[1]}"
    if article.authors:
        return article.authors[0]
    return "Unknown"


def citation_bucket(citations: int) -> str:
    if citations <= 0:
        return "0"
    if citations < 10:
        return "1-9"
    if citations < 50:
        return "10-49"
    if citations < 100:
        return "50-99"
    return "100+"


def collaboration_type(article: ArticleRecord) -> str:
    author_count = len(article.authors)
    institution_count = len(article.institutions)
    if author_count <= 1:
        author_label = "single_author"
    elif author_count <= 3:
        author_label = "small_team"
    elif author_count <= 10:
        author_label = "medium_team"
    else:
        author_label = "large_team"
    if institution_count <= 1:
        institution_label = "single_institution"
    else:
        institution_label = "multi_institution"
    return f"{author_label}_{institution_label}"


def topic_keywords(subdomain: str, articles: list[ArticleRecord], limit: int = 8) -> list[str]:
    """Extract readable keywords for one clustered topic."""
    counter = Counter()
    label = str(subdomain or "").replace("Topic_", "").replace("_", " ")
    for token in keyword_tokens(label):
        counter[token] += 3
    for article in articles:
        text = " ".join([article.title, article.abstract, article.problem_statement, article.solution_summary or ""])
        for token in keyword_tokens(text):
            counter[token] += 1
    return [token for token, _ in counter.most_common(limit)]


def keyword_tokens(text: str) -> list[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "into", "using",
        "study", "paper", "article", "research", "analysis", "model", "models",
        "based", "data", "results", "here", "show", "over", "under", "between",
    }
    return [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", (text or "").casefold())
        if token not in stopwords
    ]


def topic_trend(articles: list[ArticleRecord]) -> str:
    years = [int(year) for year in [extract_year(article.publish_date) for article in articles] if year]
    if not years:
        return "unknown"
    if len(set(years)) == 1:
        return "new"
    latest = max(years)
    earliest = min(years)
    recent_count = sum(year >= latest - 1 for year in years)
    early_count = sum(year <= earliest + 1 for year in years)
    if recent_count > early_count:
        return "rising"
    if recent_count < early_count:
        return "declining"
    return "stable"


def recommendation_type(article: ArticleRecord) -> str:
    if is_review_article(article):
        return "review_entry"
    year = extract_year(article.publish_date)
    if year and int(year) >= datetime.now().year - 3:
        return "recent_high_potential"
    if int(article.citation_count or 0) >= 100:
        return "classic"
    return "important"


def citation_score_from_max(citations: int, max_citations: int) -> float:
    if citations <= 0 or max_citations <= 0:
        return 0.0
    return min(1.0, math.log1p(citations) / math.log1p(max_citations))


def recency_score(publish_date: str) -> float:
    year = extract_year(publish_date)
    if not year:
        return 0.45
    age = max(0, datetime.now().year - int(year))
    return max(0.20, 1.0 - min(age, 20) / 20)


def metadata_completeness(article: ArticleRecord) -> float:
    fields = [
        article.title,
        article.doi,
        article.journal,
        article.publish_date,
        article.authors,
        article.institutions,
        article.abstract,
        article.citation_count is not None,
        article.subdomain,
    ]
    return round(sum(bool(field) for field in fields) / len(fields), 3)


def is_review_article(article: ArticleRecord) -> bool:
    value = " ".join([article.article_type or "", article.title or ""]).casefold()
    return "review" in value or "survey" in value


def is_research_article(article: ArticleRecord) -> bool:
    value = (article.article_type or "").casefold()
    if not value:
        return not is_review_article(article)
    return not any(marker in value for marker in ["review", "editorial", "comment", "news", "perspective"])


def median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return round((ordered[middle - 1] + ordered[middle]) / 2, 2)


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def top_rows_with_other(rows: list[dict], top_n: int, label_key: str) -> list[dict]:
    if top_n <= 0 or len(rows) <= top_n:
        return [dict(row) for row in rows]
    head = [dict(row) for row in rows[:top_n]]
    tail = rows[top_n:]
    other = {
        label_key: f"其他领域 ({len(tail)} 类)",
        "paper_count": sum(int(row.get("paper_count") or 0) for row in tail),
        "citation_count": sum(int(row.get("citation_count") or 0) for row in tail),
    }
    for key in ["pubmed_mesh_count", "openalex_count", "crossref_count", "local_rule_count", "unclassified_count"]:
        other[key] = sum(int(row.get(key) or 0) for row in tail)
    return head + [other]


def run_from_args(args) -> int:
    """CLI adapter for python -m litsurveygrp stats."""
    writer = ResearchStatsWriter(
        Path(args.manifest),
        out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        top_n=getattr(args, "top", 20),
    )
    writer.write()
    return 0

