# -*- coding: utf-8 -*-
"""Research-oriented statistics for enriched/classified paper manifests."""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from refchaser.paper_models import ArticleRecord


class ResearchStatsWriter:
    """Write research statistics that are useful for literature surveys."""

    def __init__(self, manifest_path: Path, out_dir: Path | None = None, top_n: int = 20):
        self.manifest_path = Path(manifest_path)
        self.out_dir = Path(out_dir) if out_dir else self.manifest_path.parent / "stats"
        self.top_n = top_n

    def load_manifest(self) -> list[ArticleRecord]:
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [ArticleRecord.from_manifest_dict(item) for item in data]

    def write(self, articles: list[ArticleRecord] | None = None) -> dict[str, Path]:
        articles = articles if articles is not None else self.load_manifest()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "summary": self.out_dir / "summary.json",
            "subdomains": self.out_dir / "subdomain_stats.csv",
            "years": self.out_dir / "year_trend.csv",
            "authors": self.out_dir / "author_stats.csv",
            "institutions": self.out_dir / "institution_stats.csv",
            "teams": self.out_dir / "team_stats.csv",
            "top_papers": self.out_dir / "top_papers.csv",
            "article_types": self.out_dir / "article_type_stats.csv",
            "journals": self.out_dir / "journal_stats.csv",
            "subdomain_years": self.out_dir / "subdomain_year_trend.csv",
            "citation_buckets": self.out_dir / "citation_bucket_stats.csv",
            "collaboration": self.out_dir / "collaboration_stats.csv",
        }
        self._write_json(outputs["summary"], self.summary(articles))
        self._write_rows(outputs["subdomains"], self.subdomain_stats(articles), ["subdomain", "paper_count", "citation_count"])
        self._write_rows(outputs["years"], self.year_trend(articles), ["year", "paper_count", "citation_count"])
        self._write_rows(outputs["authors"], self.author_stats(articles), ["author", "paper_count", "citation_count"])
        self._write_rows(outputs["institutions"], self.institution_stats(articles), ["institution", "paper_count", "citation_count"])
        self._write_rows(outputs["teams"], self.team_stats(articles), ["team", "paper_count", "citation_count"])
        self._write_rows(
            outputs["top_papers"],
            self.top_papers(articles),
            ["title", "doi", "journal", "year", "subdomain", "article_type", "citation_count", "citation_source"],
        )
        self._write_rows(outputs["article_types"], self.article_type_stats(articles), ["article_type", "paper_count", "citation_count"])
        self._write_rows(outputs["journals"], self.journal_stats(articles), ["journal", "paper_count", "citation_count"])
        self._write_rows(outputs["subdomain_years"], self.subdomain_year_trend(articles), ["year", "subdomain", "paper_count", "citation_count"])
        self._write_rows(outputs["citation_buckets"], self.citation_bucket_stats(articles), ["citation_bucket", "paper_count", "citation_count"])
        self._write_rows(outputs["collaboration"], self.collaboration_stats(articles), ["collaboration_type", "paper_count", "citation_count"])
        return outputs

    def summary(self, articles: list[ArticleRecord]) -> dict:
        years = [year for year in [extract_year(article.publish_date) for article in articles] if year]
        citations = [int(article.citation_count or 0) for article in articles]
        return {
            "total_papers": len(articles),
            "year_min": min(years) if years else "",
            "year_max": max(years) if years else "",
            "unique_authors": len({author for article in articles for author in article.authors}),
            "unique_institutions": len({institution for article in articles for institution in article.institutions}),
            "total_citations": sum(citations),
            "average_citations": round(sum(citations) / len(articles), 2) if articles else 0.0,
            "top_subdomains": self.subdomain_stats(articles)[: self.top_n],
            "top_authors_by_citations": self.author_stats(articles)[: self.top_n],
            "top_institutions_by_citations": self.institution_stats(articles)[: self.top_n],
            "top_journals_by_citations": self.journal_stats(articles)[: self.top_n],
        }

    def subdomain_stats(self, articles: list[ArticleRecord]) -> list[dict]:
        return self._group_counts(articles, lambda article: [article.subdomain or "Other"], "subdomain")

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


def run_from_args(args) -> int:
    """CLI adapter for python -m refchaser stats."""
    writer = ResearchStatsWriter(
        Path(args.manifest),
        out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
        top_n=getattr(args, "top", 20),
    )
    writer.write()
    return 0
