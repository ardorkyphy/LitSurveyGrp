# -*- coding: utf-8 -*-

import json
from pathlib import Path

from litsurveygrp.title_pdf_fetch import TitlePdfFetchService, dedupe_articles, title_similarity
from litsurveygrp.paper_models import ArticleRecord


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def get(self, url, params=None, timeout=None, **kwargs):
        return FakeResponse({
            "message": {
                "items": [
                    {
                        "title": ["High citation neighbor paper"],
                        "DOI": "10.1/neighbor",
                        "container-title": ["Journal"],
                        "is-referenced-by-count": 500,
                        "published": {"date-parts": [[2024]]},
                    },
                    {
                        "title": ["Precise Target Paper"],
                        "DOI": "10.1/target",
                        "container-title": ["Journal"],
                        "is-referenced-by-count": 5,
                        "published": {"date-parts": [[2025]]},
                    },
                ]
            }
        })


class FakeDownloader:
    def __init__(self, output_dir, timeout=15, domain_path_func=None):
        self.output_dir = Path(output_dir)

    def download(self, article):
        article.pdf_status = "complete"
        article.download_status = "downloaded"
        article.local_pdf_path = self.output_dir / "downloaded.pdf"
        return article


def test_fetch_pdf_title_mode_downloads_best_title_match(tmp_path):
    summary = TitlePdfFetchService(
        out_dir=tmp_path,
        title="Precise Target Paper",
        limit=5,
        top=1,
        sources=["crossref"],
        session=FakeSession(),
        downloader_cls=FakeDownloader,
    ).run()

    selected = json.loads((tmp_path / "results" / "article_manifest.json").read_text(encoding="utf-8"))
    downloaded = json.loads((tmp_path / "results" / "pdf_downloaded_manifest.json").read_text(encoding="utf-8"))

    assert summary["selected_count"] == 1
    assert selected[0]["title"] == "Precise Target Paper"
    assert downloaded[0]["title"] == "Precise Target Paper"
    assert downloaded[0]["pdf_status"] == "complete"


def test_dedupe_articles_prefers_first_doi_record():
    articles = [
        ArticleRecord(title="First", doi="10.1/demo"),
        ArticleRecord(title="Second", doi="10.1/demo"),
        ArticleRecord(title="First"),
    ]

    deduped = dedupe_articles(articles)

    assert [article.title for article in deduped] == ["First"]


def test_title_similarity_normalizes_punctuation():
    assert title_similarity("Aging, Biology: A Review", "Aging Biology A Review") > 0.95
