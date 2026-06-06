# -*- coding: utf-8 -*-

import json

from agents.domain_synthesizer_agent import DomainSynthesizerAgent, build_parser as build_domain_parser
from agents.paper_reader_agent import PaperReaderAgent, build_parser as build_paper_parser
from litsurveygrp.run_monitor import RunMonitor


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_agent_input(tmp_path):
    root = tmp_path / "agent_inputs"
    domain = root / "domain_001"
    write_json(
        domain / "domain_manifest.json",
        {
            "domain_id": "domain_001",
            "domain_name": "General Science > Methods",
            "taxonomy_source": "openalex",
            "paper_count": 2,
            "selected_paper_count": 1,
            "citation_count": 20,
            "papers": [],
        },
    )
    write_json(
        domain / "papers" / "paper_001.json",
        {
            "paper_id": "paper_001",
            "title": "A transferable method paper",
            "doi": "10.1/demo",
            "journal": "Journal",
            "year": "2025",
            "abstract": "We propose a general method and evaluate it.",
            "domain": "General Science > Methods",
            "classification_source": "openalex",
            "citation_count": 20,
            "research_value_score": 0.8,
        },
    )
    return root


def test_paper_reader_agent_writes_analysis(tmp_path):
    root = make_agent_input(tmp_path)

    summary = PaperReaderAgent(input_dir=root, provider="dry-run").run()

    out = root / "domain_001" / "paper_analysis" / "paper_001.analysis.json"
    analysis = json.loads(out.read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert analysis["research_problem"]
    assert analysis["source_basis"] == "abstract_only"
    assert analysis["confidence"] == "low"


def test_paper_reader_agent_writes_monitor(tmp_path):
    root = make_agent_input(tmp_path)

    PaperReaderAgent(input_dir=root, provider="dry-run", monitor=RunMonitor(tmp_path / "monitor")).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "paper_reader_summary.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "paper_reader"
    assert status["total"] == 1
    assert summary["monitor_status"].endswith("run_status.json")


def test_domain_synthesizer_agent_writes_synthesis_and_report(tmp_path):
    root = make_agent_input(tmp_path)
    PaperReaderAgent(input_dir=root, provider="dry-run").run()

    summary = DomainSynthesizerAgent(input_dir=root, provider="dry-run").run()

    synthesis_path = root / "domain_001" / "domain_synthesis.json"
    report_path = root / "domain_001" / "domain_report.md"
    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert synthesis["domain"] == "General Science > Methods"
    assert report_path.exists()
    assert "General Science > Methods" in report_path.read_text(encoding="utf-8")


def test_domain_synthesizer_agent_writes_monitor(tmp_path):
    root = make_agent_input(tmp_path)
    PaperReaderAgent(input_dir=root, provider="dry-run").run()

    DomainSynthesizerAgent(input_dir=root, provider="dry-run", monitor=RunMonitor(tmp_path / "monitor")).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "domain_synthesizer_summary.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "domain_synthesis"
    assert status["total"] == 1
    assert summary["monitor_status"].endswith("run_status.json")


def test_agent_cli_parsers_accept_monitor_arguments(tmp_path):
    paper_args = build_paper_parser().parse_args([
        "--input-dir",
        str(tmp_path / "agent_inputs"),
        "--monitor-dir",
        str(tmp_path / "monitor"),
    ])
    domain_args = build_domain_parser().parse_args([
        "--input-dir",
        str(tmp_path / "agent_inputs"),
        "--no-monitor",
    ])

    assert paper_args.monitor_dir.endswith("monitor")
    assert paper_args.no_monitor is False
    assert domain_args.no_monitor is True
