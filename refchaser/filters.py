# -*- coding: utf-8 -*-
"""Research-oriented article filters used before download and persistence."""

import re
from dataclasses import dataclass, field

from refchaser.paper_models import ArticleRecord


@dataclass(frozen=True)
class ArticleFilter:
    """Filter ArticleRecord instances by survey selection criteria."""

    keywords: list[str] = field(default_factory=list)
    article_types: list[str] = field(default_factory=list)
    min_citations: int | None = None
    year: int | None = None
    from_year: int | None = None
    to_year: int | None = None
    authors: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)

    def has_criteria(self) -> bool:
        return any([
            self.keywords,
            self.article_types,
            self.min_citations is not None,
            self.year is not None,
            self.from_year is not None,
            self.to_year is not None,
            self.authors,
            self.institutions,
        ])

    def needs_citation_count(self) -> bool:
        return self.min_citations is not None

    def matches(self, article: ArticleRecord) -> bool:
        """Return True when the article satisfies all configured criteria."""
        if not self.has_criteria():
            return True
        if not self._matches_keywords(article):
            return False
        if not self._matches_article_type(article):
            return False
        if not self._matches_citations(article):
            return False
        if not self._matches_year(article):
            return False
        if not self._matches_people(article.authors, self.authors):
            return False
        if not self._matches_people(article.institutions, self.institutions):
            return False
        return True

    def _matches_keywords(self, article: ArticleRecord) -> bool:
        if not self.keywords:
            return True
        haystack = normalize(" ".join([
            article.title,
            article.abstract,
            article.journal,
            article.article_type,
        ]))
        return all(normalize(keyword) in haystack for keyword in self.keywords)

    def _matches_article_type(self, article: ArticleRecord) -> bool:
        if not self.article_types:
            return True
        value = normalize(article.article_type)
        return any(normalize(article_type) in value for article_type in self.article_types)

    def _matches_citations(self, article: ArticleRecord) -> bool:
        if self.min_citations is None:
            return True
        return int(article.citation_count or 0) >= int(self.min_citations)

    def _matches_year(self, article: ArticleRecord) -> bool:
        expected_from = self.year if self.year is not None else self.from_year
        expected_to = self.year if self.year is not None else self.to_year
        if expected_from is None and expected_to is None:
            return True
        article_year = extract_year(article.publish_date)
        if article_year is None:
            return False
        if expected_from is not None and article_year < expected_from:
            return False
        if expected_to is not None and article_year > expected_to:
            return False
        return True

    def _matches_people(self, values: list[str], required_values: list[str]) -> bool:
        if not required_values:
            return True
        normalized_values = [normalize(value) for value in values]
        return any(
            normalize(required) in value
            for required in required_values
            for value in normalized_values
        )


def extract_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value or "")
    return int(match.group(0)) if match else None


def normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())
