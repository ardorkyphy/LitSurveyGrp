# -*- coding: utf-8 -*-

import json
from pathlib import Path

from litsurveygrp.agent_input import AgentInputPreparer, run_from_args, safe_pdf_name
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.run_monitor import RunMonitor


def test_agent_input_preparer_builds_domain_packages(tmp_path):
    manifest = tmp_path / "classified_manifest.json"
    articles = [
        ArticleRecord(
            title="High value causal paper",
            doi="10.1/high",
            journal="Journal A",
            publish_date="2026-01-01",
            abstract="A causal discovery method.",
            subdomain="Computer Science > Artificial Intelligence > Causal Discovery",
            classification_source="openalex",
            classification_taxonomy="OpenAlex Topics",
            classification_source_label="Computer Science > Artificial Intelligence > Causal Discovery",
            citation_count=100,
        ),
        ArticleRecord(
            title="Lower value causal paper",
            doi="10.1/low",
            journal="Journal B",
            publish_date="2024-01-01",
            abstract="Another causal discovery method.",
            subdomain="Computer Science > Artificial Intelligence > Causal Discovery",
            classification_source="openalex",
            citation_count=10,
        ),
        ArticleRecord(
            title="Aging paper",
            doi="10.1/aging",
            journal="Journal C",
            publish_date="2025-01-01",
            abstract="Aging biology.",
            subdomain="Biology > Aging > Longevity",
            classification_source="openalex",
            citation_count=50,
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles]), encoding="utf-8")

    summary = AgentInputPreparer(
        manifest_path=manifest,
        out_dir=tmp_path / "data",
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        top_domains=1,
        per_domain=1,
        project_name="demo",
    ).run()

    assert summary["project_name"] == "demo"
    assert summary["domain_count"] == 1
    package = tmp_path / "results" / "demo" / "Causal_Discovery"
    domain_manifest = json.loads((package / "domain_manifest.json").read_text(encoding="utf-8"))
    paper = json.loads((package / "papers" / "paper_001.json").read_text(encoding="utf-8"))

    assert domain_manifest["domain_name"] == "Computer Science > Artificial Intelligence > Causal Discovery"
    assert domain_manifest["paper_count"] == 2
    assert domain_manifest["selected_paper_count"] == 1
    assert paper["title"] == "High value causal paper"
    assert paper["research_value_score"] > 0


def test_agent_input_preparer_writes_monitor(tmp_path):
    manifest = tmp_path / "classified_manifest.json"
    article = ArticleRecord(
        title="Monitored paper",
        doi="10.1/monitor",
        subdomain="General Science > Methods",
        citation_count=3,
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()]), encoding="utf-8")

    AgentInputPreparer(
        manifest_path=manifest,
        out_dir=tmp_path / "data",
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        top_domains=1,
        per_domain=1,
        monitor=RunMonitor(tmp_path / "monitor"),
    ).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "prepare_agent_input"
    assert status["processed"] == 1
    assert "agent input" in status["run_name"].casefold()


def test_agent_input_preparer_can_select_top_downloaded_pdfs(tmp_path, monkeypatch):
    manifest = tmp_path / "pdf_downloaded_manifest.json"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF demo")
    articles = [
        ArticleRecord(
            title="Downloaded paper",
            doi="10.1/downloaded",
            journal="Journal",
            publish_date="2025-01-01",
            abstract="Downloaded full text paper.",
            subdomain="Biology > Aging > Longevity",
            citation_count=100,
            local_pdf_path=pdf,
            pdf_status="complete",
        ),
        ArticleRecord(
            title="No PDF paper",
            doi="10.1/no-pdf",
            journal="Journal",
            publish_date="2025-01-01",
            abstract="Metadata only paper.",
            subdomain="Biology > Aging > Longevity",
            citation_count=1000,
        ),
    ]
    manifest.write_text(json.dumps([article.to_manifest_dict() for article in articles]), encoding="utf-8")
    monkeypatch.setattr("litsurveygrp.agent_input.PdfReferenceExtractor.extract_text", lambda self, path: "Full text from PDF.")

    summary = AgentInputPreparer(
        manifest_path=manifest,
        out_dir=tmp_path / "data",
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        selection="top-downloaded-pdfs",
        top_papers=30,
        copy_pdfs=True,
        extract_pdf_text=True,
    ).run()

    package = tmp_path / "results" / "analysis" / "Longevity"
    paper = json.loads((package / "papers" / "paper_001.json").read_text(encoding="utf-8"))
    assert summary["selection"] == "top-downloaded-pdfs"
    assert summary["packages"][0]["selected_paper_count"] == 1
    assert paper["title"] == "Downloaded paper"
    assert paper["packaged_pdf_path"] == str(pdf)
    assert paper["text_path"] == str(Path("extracted_text") / "paper_001.txt")
    assert (package / paper["text_path"]).read_text(encoding="utf-8") == "Full text from PDF."


def test_agent_input_zero_max_text_chars_keeps_full_text(tmp_path, monkeypatch):
    manifest = tmp_path / "pdf_downloaded_manifest.json"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF demo")
    article = ArticleRecord(
        title="Downloaded paper",
        doi="10.1/downloaded",
        journal="Journal",
        publish_date="2025-01-01",
        abstract="Downloaded full text paper.",
        subdomain="Biology > Aging > Longevity",
        citation_count=100,
        local_pdf_path=pdf,
        pdf_status="complete",
    )
    manifest.write_text(json.dumps([article.to_manifest_dict()]), encoding="utf-8")
    full_text = "A" * 8000
    monkeypatch.setattr("litsurveygrp.agent_input.PdfReferenceExtractor.extract_text", lambda self, path: full_text)

    AgentInputPreparer(
        manifest_path=manifest,
        out_dir=tmp_path / "data",
        papers_dir=tmp_path / "papers",
        results_dir=tmp_path / "results",
        selection="top-downloaded-pdfs",
        top_papers=1,
        extract_pdf_text=True,
        max_text_chars=0,
    ).run()

    text_path = tmp_path / "results" / "analysis" / "Longevity" / "extracted_text" / "paper_001.txt"
    assert text_path.read_text(encoding="utf-8") == full_text


def test_safe_pdf_name_preserves_pdf_suffix_when_truncated():
    name = safe_pdf_name("A" * 200 + ".pdf", max_length=120)

    assert len(name) == 120
    assert name.endswith(".pdf")


def test_prepare_agent_input_cli_adapter(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        out_dir = str(tmp_path / "agent_inputs")
        papers_dir = str(tmp_path / "papers")
        results_dir = str(tmp_path / "results")
        project_name = "demo"
        top_domains = 3
        per_domain = 7
        selection = "top-downloaded-pdfs"
        top_papers = 11
        copy_pdfs = True
        extract_pdf_text = False
        max_text_chars = 123
        monitor_dir = str(tmp_path / "monitor")
        no_monitor = False

    captured = {}

    def fake_run(self):
        captured["manifest_path"] = self.manifest_path
        captured["out_dir"] = self.out_dir
        captured["papers_dir"] = self.papers_dir
        captured["results_dir"] = self.results_dir
        captured["top_domains"] = self.top_domains
        captured["per_domain"] = self.per_domain
        captured["selection"] = self.selection
        captured["top_papers"] = self.top_papers
        captured["copy_pdfs"] = self.copy_pdfs
        captured["max_text_chars"] = self.max_text_chars
        captured["monitor"] = self.monitor
        return {}

    monkeypatch.setattr(AgentInputPreparer, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["out_dir"].name == "agent_inputs"
    assert captured["papers_dir"].name == "papers"
    assert captured["results_dir"].name == "results"
    assert captured["top_domains"] == 3
    assert captured["per_domain"] == 7
    assert captured["selection"] == "top-downloaded-pdfs"
    assert captured["top_papers"] == 11
    assert captured["copy_pdfs"] is True
    assert captured["max_text_chars"] == 123
    assert captured["monitor"].out_dir.name == "monitor"
