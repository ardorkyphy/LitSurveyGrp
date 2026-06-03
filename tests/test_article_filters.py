# -*- coding: utf-8 -*-

from refchaser.filters import ArticleFilter, extract_year, normalize
from refchaser.paper_models import ArticleRecord


def test_article_filter_requires_all_keywords():
    article = ArticleRecord(
        title="Senescence biomarker atlas",
        abstract="This aging study maps immune cells.",
    )

    assert ArticleFilter(keywords=["senescence", "immune"]).matches(article)
    assert not ArticleFilter(keywords=["senescence", "metabolism"]).matches(article)


def test_article_filter_matches_type_citations_year_author_and_institution():
    article = ArticleRecord(
        title="Review on aging",
        article_type="Review Article",
        publish_date="2024/05/01",
        citation_count=25,
        authors=["Alice Zhang", "Bob Li"],
        institutions=["Institute of Aging Research"],
    )
    article_filter = ArticleFilter(
        article_types=["review"],
        min_citations=20,
        from_year=2021,
        to_year=2025,
        authors=["zhang"],
        institutions=["aging research"],
    )

    assert article_filter.matches(article)
    assert not ArticleFilter(min_citations=30).matches(article)
    assert not ArticleFilter(from_year=2025).matches(article)
    assert not ArticleFilter(article_types=["article"], authors=["chen"]).matches(article)


def test_article_filter_single_year_overrides_range():
    article = ArticleRecord(title="Paper", publish_date="2024-01-01")

    assert ArticleFilter(year=2024, from_year=2020, to_year=2021).matches(article)
    assert not ArticleFilter(year=2023, from_year=2024, to_year=2024).matches(article)


def test_extract_year_and_normalize_helpers():
    assert extract_year("Published 2026/01") == 2026
    assert extract_year("") is None
    assert normalize("  Alice   ZHANG ") == "alice zhang"
