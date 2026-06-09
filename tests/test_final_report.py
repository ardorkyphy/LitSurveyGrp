# -*- coding: utf-8 -*-

import json

from litsurveygrp.__main__ import build_parser
from litsurveygrp.final_report import FinalSurveyReportBuilder, run_from_args


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_report_inputs(tmp_path):
    results = tmp_path / "results"
    agent = results / "Neuroscience"
    reports = tmp_path / "reports" / "Neuroscience" / "data"
    domain_dir = agent / "Neuroscience" / "Brain-Computer_Interfaces"
    analysis_dir = results / "Neuroscience" / "Brain-Computer_Interfaces"
    write_json(
        reports / "pipeline_report.json",
        {
            "query": "AI in Neuroscience",
            "final_manifest": str(reports / "classified_manifest.json"),
            "metadata_sources": ["openalex"],
            "collection_mode": "metadata_only",
        },
    )
    write_json(
        reports / "stats" / "summary.json",
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
        reports / "stats" / "research_profile.json",
        {
            "review_entry_points": [
                {"title": "Review paper", "year": "2024", "journal": "Journal", "doi": "10.1/review"}
            ],
            "classic_papers": [],
            "recent_high_potential_papers": [],
            "growing_topics": [],
        },
    )
    write_json(reports / "pdf_download_summary.json", {"selected_for_download": 1, "completed_pdfs": 1})
    write_json(reports / "classified_manifest.json", [{"title": "Paper", "doi": "10.1/paper"}])

    write_json(agent / "agent_input_summary.json", {"project_name": "ai_in_neuroscience", "domain_count": 1})
    write_json(analysis_dir / "paper_reader_summary.json", {"provider": "dry-run", "written_count": 1})
    write_json(analysis_dir / "domain_synthesizer_summary.json", {"provider": "dry-run", "written_count": 1})
    write_json(
        domain_dir / "domain_manifest.json",
        {
            "domain_id": "domain_001",
            "domain_name": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "major_domain": "Neuroscience",
            "subdomain_dir": "Brain-Computer_Interfaces",
            "taxonomy_source": "openalex",
            "paper_count": 2,
            "selected_paper_count": 1,
        },
    )
    write_json(
        analysis_dir / "domain_synthesis.json",
        {
            "domain": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "one_sentence_summary": "Brain-computer interface studies connect neural signals and AI systems.",
            "core_problem_system": ["Decode neural signals."],
            "method_system": ["Signal processing and machine learning."],
            "research_gaps": ["Improve cross-cohort robustness."],
            "evidence_index": [{"claim": "Neural decoding requires robust cross-cohort validation.", "papers": ["paper_001"]}],
            "confidence": "medium",
            "domain_evidence_coverage": {
                "candidate_papers": 2,
                "selected_papers": 1,
                "packaged_papers": 1,
                "pdf_available": 1,
                "pdf_text_available": 0,
                "analyzed_papers": 1,
                "papers_analyzed_from_pdf_text": 0,
                "papers_analyzed_from_abstract_only": 1,
                "papers_analyzed_from_metadata_only": 0,
                "papers_with_selected_evidence_chunks": 1,
                "failed_or_missing_analyses": 0,
                "reliability": "medium",
                "reliability_note": "The domain synthesis has partial full-text support.",
            },
        },
    )
    write_json(
        domain_dir / "papers" / "paper_001.json",
        {
            "paper_id": "paper_001",
            "title": "Neural decoding paper",
            "year": "2025",
            "journal": "Journal",
            "citation_count": 20,
            "domain": "Neuroscience > Cognitive Neuroscience > Brain-Computer Interfaces",
            "doi": "10.1/decoding",
        },
    )
    write_json(
        analysis_dir / "paper_001.analysis.json",
        {
            "research_problem": "Decode neural signals.",
            "core_findings": ["Neural decoding requires robust cross-cohort validation."],
            "source_basis": "abstract_only",
            "confidence": "medium",
            "supporting_text": ["Brain-computer interface studies connect neural signals and AI systems."],
            "evidence_chunks": [
                {
                    "chunk_id": "paper_001:discussion:001",
                    "section": "discussion",
                    "score": 4.2,
                    "reasons": ["findings", "limitations"],
                }
            ],
        },
    )
    return results, agent


def test_final_report_builder_writes_markdown_and_html(tmp_path):
    results, agent = make_report_inputs(tmp_path)

    outputs = FinalSurveyReportBuilder(results, agent_dir=agent).build()

    markdown = outputs["markdown"].read_text(encoding="utf-8")
    html = outputs["html"].read_text(encoding="utf-8")
    assert outputs["markdown"] == tmp_path / "reports" / "Neuroscience" / "Brain-Computer_Interfaces" / "final_survey_report.md"
    assert outputs["html"] == tmp_path / "reports" / "Neuroscience" / "Brain-Computer_Interfaces" / "final_survey_report.html"
    assert "AI in Neuroscience: A Multi-Domain Literature Survey" in markdown
    assert "## Abstract" in markdown
    assert "## 4. Domain-Level Findings" in markdown
    assert "Brain-computer interface studies" in markdown
    assert "Evidence trace:" in markdown
    assert "### 3.3 Domain Evidence Coverage" in markdown
    assert "reliability is `medium`" in markdown
    assert "paper_001:discussion:001" in markdown
    assert "dry-run" in markdown
    assert "<html" in html


def test_final_report_skips_invalid_agent_outputs(tmp_path):
    results, agent = make_report_inputs(tmp_path)
    write_json(
        results / "Neuroscience" / "Brain-Computer_Interfaces" / "paper_002.analysis.json",
        {
            "validation_status": "invalid",
            "research_problem": "This failed result should not be included.",
            "source_basis": "abstract_only",
            "confidence": "low",
        },
    )
    write_json(
        agent / "Neuroscience" / "Brain-Computer_Interfaces" / "papers" / "paper_002.json",
        {
            "title": "Invalid paper",
            "year": "2026",
            "journal": "Journal",
            "citation_count": 1,
        },
    )

    data = FinalSurveyReportBuilder(results, agent_dir=agent).load_context()

    assert len(data["domains"][0]["analyses"]) == 1
    assert data["domains"][0]["analyses"][0]["paper"]["title"] == "Neural decoding paper"


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
    assert captured["agent_dir"] == results / "Neuroscience"
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
