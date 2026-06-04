# -*- coding: utf-8 -*-

import csv
import json
from pathlib import Path

from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.pdf_download_stage import TopPdfDownloadService, run_from_args


class FakeDownloader:
    calls = []

    def __init__(self, output_dir, timeout=15):
        self.output_dir = Path(output_dir)
        self.timeout = timeout

    def download(self, article):
        FakeDownloader.calls.append(article.title)
        path = self.output_dir / "all_papers" / f"{article.title}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF- fake")
        article.local_pdf_path = path
        article.download_status = "downloaded"
        article.pdf_status = "complete"
        article.error = ""
        return article


def test_top_pdf_download_service_ranks_and_downloads_top_n(tmp_path):
    FakeDownloader.calls = []
    manifest = tmp_path / "中文结果" / "classified_manifest.json"
    papers_dir = tmp_path / "中文papers"
    results_dir = tmp_path / "中文结果"
    results_dir.mkdir()
    articles = [
        ArticleRecord(
            title="Low value",
            doi="10.1/low",
            journal="Unknown Journal",
            publish_date="2010",
            citation_count=1,
            classification_confidence=0.2,
        ),
        ArticleRecord(
            title="High value",
            doi="10.1/high",
            journal="Nature Aging",
            publish_date="2026",
            citation_count=50,
            classification_confidence=0.9,
            abstract="complete metadata",
        ),
        ArticleRecord(
            title="Medium value",
            doi="10.1/mid",
            journal="Science",
            publish_date="2024",
            citation_count=10,
            classification_confidence=0.6,
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles], ensure_ascii=False), encoding="utf-8")
    service = TopPdfDownloadService(
        manifest,
        papers_dir=papers_dir,
        results_dir=results_dir,
        top=2,
        downloader_cls=FakeDownloader,
    )

    outputs = service.run()

    assert FakeDownloader.calls == ["High value", "Medium value"]
    updated = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    assert [item["pdf_status"] for item in updated] == ["unchecked", "complete", "complete"]
    rows = read_csv(outputs["ranking"])
    assert rows[0]["title"] == "High value"
    assert rows[0]["selected_for_download"] == "True"
    assert rows[1]["title"] == "Medium value"
    assert rows[2]["selected_for_download"] == "False"
    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    assert summary["total_candidates"] == 3
    assert summary["selected_for_download"] == 2
    assert summary["completed_pdfs"] == 2


def test_top_pdf_download_service_can_skip_existing_and_require_doi(tmp_path):
    FakeDownloader.calls = []
    existing_pdf = tmp_path / "papers" / "all_papers" / "existing.pdf"
    existing_pdf.parent.mkdir(parents=True)
    existing_pdf.write_bytes(b"%PDF- existing")
    manifest = tmp_path / "manifest.json"
    articles = [
        ArticleRecord(
            title="Already downloaded",
            doi="10.1/existing",
            journal="Nature Aging",
            publish_date="2026",
            citation_count=100,
            local_pdf_path=existing_pdf,
            download_status="downloaded",
            pdf_status="complete",
        ),
        ArticleRecord(
            title="No DOI",
            journal="Nature Aging",
            publish_date="2026",
            citation_count=90,
        ),
        ArticleRecord(
            title="Eligible",
            doi="10.1/eligible",
            journal="Nature Aging",
            publish_date="2026",
            citation_count=80,
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles]), encoding="utf-8")
    service = TopPdfDownloadService(
        manifest,
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        top=3,
        require_doi=True,
        downloader_cls=FakeDownloader,
    )

    outputs = service.run()

    assert FakeDownloader.calls == ["Eligible"]
    rows = read_csv(outputs["ranking"])
    reasons = {row["title"]: row["eligibility_reason"] for row in rows}
    assert reasons["Already downloaded"] == "already_complete"
    assert reasons["No DOI"] == "missing_doi"
    assert reasons["Eligible"] == "eligible"


def test_pdf_download_stage_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        papers_dir = str(tmp_path / "papers")
        results_dir = str(tmp_path / "results")
        top = 7
        min_value_score = 0.4
        download_workers = 3
        timeout = 9
        require_doi = True
        include_existing = True
        no_retry_oa_resolution = True
        out_manifest_name = "custom_manifest.json"

    captured = {}

    def fake_run(self):
        captured["manifest_path"] = self.manifest_path
        captured["papers_dir"] = self.papers_dir
        captured["results_dir"] = self.results_dir
        captured["top"] = self.top
        captured["min_value_score"] = self.min_value_score
        captured["download_workers"] = self.download_workers
        captured["timeout"] = self.timeout
        captured["require_doi"] = self.require_doi
        captured["skip_existing"] = self.skip_existing
        captured["retry_oa_resolution"] = self.retry_oa_resolution
        captured["output_manifest_name"] = self.output_manifest_name
        return {}

    monkeypatch.setattr(TopPdfDownloadService, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["top"] == 7
    assert captured["min_value_score"] == 0.4
    assert captured["download_workers"] == 3
    assert captured["timeout"] == 9
    assert captured["require_doi"] is True
    assert captured["skip_existing"] is False
    assert captured["retry_oa_resolution"] is False
    assert captured["output_manifest_name"] == "custom_manifest.json"


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
