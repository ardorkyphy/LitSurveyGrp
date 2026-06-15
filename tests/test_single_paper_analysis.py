# -*- coding: utf-8 -*-

import json

from litsurveygrp.single_paper_analysis import SinglePaperAnalysisService, render_single_paper_report


class FakeExtractor:
    def extract_text(self, pdf_path):
        return "Abstract\nThis paper studies a precise research problem.\nMethods\nIt uses a simple method."


def test_single_paper_analysis_packages_pdf_and_writes_report(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF demo")

    summary = SinglePaperAnalysisService(
        pdf_path=pdf,
        out_dir=tmp_path / "single",
        title="Local PDF Paper",
        provider="dry-run",
        extractor=FakeExtractor(),
    ).run()

    package_dir = tmp_path / "single" / "results" / "single_paper" / "Local_PDF_Paper"
    paper = json.loads((package_dir / "papers" / "paper_001.json").read_text(encoding="utf-8"))
    analysis = json.loads((package_dir / "paper_001.analysis.json").read_text(encoding="utf-8"))
    report = tmp_path / "single" / "reports" / "single_paper" / "Local_PDF_Paper" / "paper_report.md"

    assert paper["title"] == "Local PDF Paper"
    assert paper["text_path"] == "extracted_text\\paper_001.txt" or paper["text_path"] == "extracted_text/paper_001.txt"
    assert analysis["source_basis"] == "pdf_text"
    assert report.exists()
    assert "# Local PDF Paper" in report.read_text(encoding="utf-8")
    assert summary["markdown"] == str(report)


def test_render_single_paper_report_includes_analysis_lists():
    markdown = render_single_paper_report(
        {"title": "Demo", "doi": "10.1/demo", "journal": "Journal", "year": "2026"},
        {
            "source_basis": "pdf_text",
            "research_problem": "Problem",
            "core_findings": ["Finding"],
            "methods": ["Method"],
        },
        {"provider": "dry-run", "model": "dry-run"},
    )

    assert "## Core Findings" in markdown
    assert "- Finding" in markdown
    assert "- Agent provider: dry-run" in markdown
