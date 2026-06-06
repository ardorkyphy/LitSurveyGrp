# -*- coding: utf-8 -*-

import json

from litsurveygrp.__main__ import build_parser
from litsurveygrp.final_report import FinalSurveyReportBuilder, run_from_args


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_report_inputs(tmp_path):
    results = tmp_path / "results"
    agent = tmp_path / "agent_inputs"
    write_json(
        results / "pipeline_report.json",
        {
            "query": "AI in Neuroscience",
            "final_manifest": str(results / "classified_manifest.json"),
            "metadata_sources": ["openalex"],
            "collection_mode": "metadata_only",
        },
    )
    write_json(
        results / "stats" / "summary.json",
        {
            "total_papers": 2,
            "year_min": "2020",
            "year_max": "2026",
            "unique_authors": 4,
            "unique_institutions": 2,
            "total_citations": 30,
            "average_citations": 15.0,
            "median_citations": 15.0,
            "classification_sources": [{"classification_source": "openalex", "paper_count": 2}],
            "top_subdomains": [
                {"subdomain": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces", "paper_count": 2, "citation_count": 30}
            ],
            "top_journals_by_citations": [{"journal": "Journal", "paper_count": 2, "citation_count": 30}],
            "top_institutions_by_citations": [{"institution": "Institute", "paper_count": 2, "citation_count": 30}],
        },
    )
    write_json(
        results / "stats" / "research_profile.json",
        {
            "review_entry_points": [
                {"title": "Review paper", "year": "2024", "journal": "Journal", "doi": "10.1/review"}
            ],
            "classic_papers": [],
            "recent_high_potential_papers": [],
            "growing_topics": [],
        },
    )
    write_json(results / "pdf_download_summary.json", {"selected_for_download": 1, "completed_pdfs": 1})
    write_json(results / "classified_manifest.json", [{"title": "Paper", "doi": "10.1/paper"}])

    write_json(agent / "agent_input_summary.json", {"project_name": "ai_in_neuroscience", "domain_count": 1})
    write_json(agent / "paper_reader_summary.json", {"provider": "dry-run", "written_count": 1})
    write_json(agent / "domain_synthesizer_summary.json", {"provider": "dry-run", "written_count": 1})
    write_json(
        agent / "domain_001" / "domain_manifest.json",
        {
            "domain_id": "domain_001",
            "domain_name": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "taxonomy_source": "openalex",
            "paper_count": 2,
            "selected_paper_count": 1,
        },
    )
    write_json(
        agent / "domain_001" / "domain_synthesis.json",
        {
            "domain": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "one_sentence_summary": "Brain-computer interface studies connect neural signals and AI systems.",
            "core_problem_system": ["Decode neural signals."],
            "method_system": ["Signal processing and machine learning."],
            "research_gaps": ["Improve cross-cohort robustness."],
            "confidence": "medium",
        },
    )
    write_json(
        agent / "domain_001" / "papers" / "paper_001.json",
        {
            "title": "Neural decoding paper",
            "year": "2025",
            "journal": "Journal",
            "citation_count": 20,
            "domain": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "doi": "10.1/decoding",
        },
    )
    write_json(
        agent / "domain_001" / "paper_analysis" / "paper_001.analysis.json",
        {
            "research_problem": "Decode neural signals.",
            "source_basis": "abstract_only",
            "confidence": "medium",
        },
    )
    return results, agent


def test_final_report_builder_writes_markdown_and_html(tmp_path):
    results, agent = make_report_inputs(tmp_path)

    outputs = FinalSurveyReportBuilder(results, agent_dir=agent).build()

    markdown = outputs["markdown"].read_text(encoding="utf-8")
    html = outputs["html"].read_text(encoding="utf-8")
    assert "AI in Neuroscience: A Multi-Domain Literature Survey" in markdown
    assert "## Abstract" in markdown
    assert "## 4. Domain-Level Findings" in markdown
    assert "Brain-computer interface studies" in markdown
    assert "dry-run" in markdown
    assert "<html" in html


def test_final_report_cli_adapter(monkeypatch, tmp_path):
    results, agent = make_report_inputs(tmp_path)
    captured = {}

    def fake_build(self):
        captured["results_dir"] = self.results_dir
        captured["agent_dir"] = self.agent_dir
        captured["out"] = self.out
        return {}

    monkeypatch.setattr(FinalSurveyReportBuilder, "build", fake_build)

    class Args:
        results_dir = str(results)
        agent_dir = str(agent)
        out = str(results / "custom.md")
        html_out = ""
        title = "Custom Title"
        max_domains = 5
        max_papers_per_domain = 3
        max_recommended_papers = 4

    assert run_from_args(Args()) == 0
    assert captured["results_dir"].name == "results"
    assert captured["agent_dir"].name == "agent_inputs"
    assert captured["out"].name == "custom.md"


def test_cli_report_arguments():
    args = build_parser().parse_args([
        "report",
        "--results-dir",
        "results",
        "--agent-dir",
        "agent_inputs",
        "--out",
        "report.md",
        "--html-out",
        "report.html",
        "--max-domains",
        "6",
    ])

    assert args.command == "report"
    assert args.results_dir == "results"
    assert args.agent_dir == "agent_inputs"
    assert args.out == "report.md"
    assert args.html_out == "report.html"
    assert args.max_domains == 6
