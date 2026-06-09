# -*- coding: utf-8 -*-

import json

from agents.domain_synthesizer_agent import DomainSynthesizerAgent, build_parser as build_domain_parser
from agents.paper_reader_agent import PaperReaderAgent, build_parser as build_paper_parser
from litsurveygrp.run_monitor import RunMonitor


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_agent_input(tmp_path):
    root = tmp_path / "data"
    domain = root / "analysis" / "Methods"
    write_json(
        domain / "domain_manifest.json",
        {
            "domain_id": "domain_001",
            "domain_name": "General Science > Methods",
            "major_domain": "analysis",
            "subdomain_dir": "Methods",
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


def analysis_dir(root):
    return root.parent / "results" / "analysis" / "Methods"


def report_dir(root):
    return root.parent / "reports" / "analysis" / "Methods"


class StaticLLMClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, **kwargs):
        return self.response


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([
                1.0 if any(term in lowered for term in ["gap", "problem", "objective"]) else 0.0,
                1.0 if any(term in lowered for term in ["method", "pipeline", "data", "model"]) else 0.0,
                1.0 if any(term in lowered for term in ["result", "finding", "evaluate"]) else 0.0,
                1.0 if any(term in lowered for term in ["limitation", "future", "robust"]) else 0.0,
            ])
        return vectors


class FakeRerankerModel:
    def predict(self, pairs):
        return [0.5 for _ in pairs]


def patch_evidence_models(monkeypatch):
    monkeypatch.setattr("agents.evidence.load_deployed_embedding_model", lambda: FakeEmbeddingModel())
    monkeypatch.setattr("agents.evidence.load_deployed_reranker_model", lambda: FakeRerankerModel())


def valid_paper_response(supporting_text=None):
    return {
        "research_problem": "Develop and evaluate a general method.",
        "background_gap": "Existing methods need broader evaluation.",
        "study_object": "A general method.",
        "data_or_materials": ["evaluation data"],
        "methods": ["method evaluation"],
        "method_pipeline": "Propose a method and evaluate it.",
        "core_findings": ["The method can be evaluated."],
        "evidence_type": "abstract",
        "limitations": ["Not enough full-text evidence."],
        "open_questions": ["How robust is the method?"],
        "reusable_resources": [],
        "source_basis": "abstract_only",
        "confidence": "medium",
        "supporting_text": supporting_text or [],
    }


def valid_domain_response(paper_title="A transferable method paper"):
    return {
        "domain": "General Science > Methods",
        "one_sentence_summary": "This domain studies transferable methods.",
        "core_problem_system": ["Develop transferable methods."],
        "method_system": ["Method evaluation."],
        "problem_method_matrix": [
            {
                "problem": "Develop transferable methods.",
                "methods": ["Method evaluation."],
                "representative_papers": [paper_title],
            }
        ],
        "mature_findings": ["Methods can be evaluated."],
        "controversies_or_uncertainties": [],
        "research_gaps": ["Assess robustness."],
        "recommended_reading_order": [{"title": paper_title, "reason": "Representative entry point."}],
        "candidate_research_questions": ["How robust is the method?"],
        "evidence_index": [{"claim": "Methods are evaluated.", "papers": [paper_title]}],
        "confidence": "medium",
    }


def test_paper_reader_agent_writes_analysis(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)

    summary = PaperReaderAgent(input_dir=root, provider="dry-run").run()

    out = analysis_dir(root) / "paper_001.analysis.json"
    analysis = json.loads(out.read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert analysis["research_problem"]
    assert analysis["source_basis"] == "abstract_only"
    assert analysis["confidence"] == "low"


def test_paper_reader_agent_accepts_grounded_supporting_text(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)

    summary = PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["We propose a general method and evaluate it."])),
    ).run()

    out = analysis_dir(root) / "paper_001.analysis.json"
    analysis = json.loads(out.read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert summary["failed_count"] == 0
    assert analysis["validation_status"] == "valid"
    assert analysis["unsupported_supporting_text"] == []


def test_paper_reader_agent_writes_error_for_unsupported_evidence(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)

    summary = PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["This sentence is not in the supplied paper."])),
    ).run()

    out = analysis_dir(root) / "paper_001.analysis.json"
    error = analysis_dir(root) / "paper_001.analysis.error.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert summary["written_count"] == 1
    assert summary["failed_count"] == 0
    assert not error.exists()
    assert payload["validation_status"] == "valid"
    assert payload["supporting_text"] == []
    assert payload["validation_warnings"] == ["$.supporting_text: removed unsupported snippet 1"]


def test_paper_reader_agent_reads_package_relative_text_path(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    domain = root / "analysis" / "Methods"
    (domain / "extracted_text").mkdir()
    (domain / "extracted_text" / "paper_001.txt").write_text("Full text evidence.", encoding="utf-8")
    paper_path = domain / "papers" / "paper_001.json"
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    paper["text_path"] = "extracted_text/paper_001.txt"
    paper_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")

    PaperReaderAgent(input_dir=root, provider="dry-run").run()

    out = analysis_dir(root) / "paper_001.analysis.json"
    analysis = json.loads(out.read_text(encoding="utf-8"))
    assert analysis["source_basis"] == "pdf_text"


def test_paper_reader_agent_uses_evidence_chunks_by_default(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    domain = root / "analysis" / "Methods"
    (domain / "extracted_text").mkdir()
    (domain / "extracted_text" / "paper_001.txt").write_text(
        """
Introduction
This paper addresses a major evaluation gap.
Methods
We propose a general method and evaluate it.
Results
The method can be evaluated with clear evidence.
""",
        encoding="utf-8",
    )
    paper_path = domain / "papers" / "paper_001.json"
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    paper["text_path"] = "extracted_text/paper_001.txt"
    paper_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["We propose a general method and evaluate it."])),
        max_chunks_per_paper=4,
        max_chunk_chars=500,
    ).run()

    out = analysis_dir(root) / "paper_001.analysis.json"
    analysis = json.loads(out.read_text(encoding="utf-8"))
    assert summary["input_mode"] == "evidence-chunks"
    assert analysis["validation_status"] == "valid"
    assert analysis["evidence_chunks"]
    assert analysis["evidence_chunks"][0]["selection_method"] == "bge_embedding_reranker"
    assert "embedding_score" in analysis["evidence_chunks"][0]
    assert analysis["evidence_coverage"]["selected_sections"]


def test_paper_reader_agent_writes_monitor(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)

    PaperReaderAgent(input_dir=root, provider="dry-run", monitor=RunMonitor(tmp_path / "monitor")).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    summary = json.loads((analysis_dir(root) / "paper_reader_summary.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "paper_reader"
    assert status["total"] == 1
    assert summary["monitor_status"].endswith("run_status.json")


def test_domain_synthesizer_agent_writes_synthesis_and_report(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    PaperReaderAgent(input_dir=root, provider="dry-run").run()

    summary = DomainSynthesizerAgent(input_dir=root, provider="dry-run").run()

    synthesis_path = analysis_dir(root) / "domain_synthesis.json"
    report_path = report_dir(root) / "domain_report.md"
    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    assert summary["written_count"] == 1
    assert synthesis["domain"] == "General Science > Methods"
    assert synthesis["domain_evidence_coverage"]["selected_papers"] == 1
    assert "## Evidence Coverage" in report
    assert "Papers selected for agent analysis: 1" in report
    assert report_path.exists()
    assert "General Science > Methods" in report_path.read_text(encoding="utf-8")


def test_domain_synthesizer_uses_only_valid_paper_analyses(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["We propose a general method and evaluate it."])),
    ).run()
    write_json(
        analysis_dir(root) / "paper_999.analysis.error.json",
        {
            "validation_status": "invalid",
            "validation_errors": ["bad evidence"],
            "analysis": {"research_problem": "Do not include me."},
        },
    )
    agent = DomainSynthesizerAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_domain_response()),
    )

    payload = agent.build_payload(root / "analysis" / "Methods")
    summary = agent.run()

    assert len(payload["paper_analyses"]) == 1
    assert summary["written_count"] == 1
    assert summary["failed_count"] == 0


def test_domain_synthesizer_writes_error_for_unknown_evidence_paper(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["We propose a general method and evaluate it."])),
    ).run()

    summary = DomainSynthesizerAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_domain_response("Unknown paper title")),
    ).run()

    out = analysis_dir(root) / "domain_synthesis.json"
    error = analysis_dir(root) / "domain_synthesis.error.json"
    payload = json.loads(error.read_text(encoding="utf-8"))
    assert summary["written_count"] == 0
    assert summary["failed_count"] == 1
    assert not out.exists()
    assert payload["validation_status"] == "invalid"
    assert "Unknown paper title" in payload["synthesis"]["unknown_evidence_papers"]


def test_domain_synthesizer_accepts_paper_id_evidence(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    PaperReaderAgent(
        input_dir=root,
        llm_client=StaticLLMClient(valid_paper_response(["We propose a general method and evaluate it."])),
    ).run()
    response = valid_domain_response("A transferable method paper")
    response["evidence_index"] = [{"claim": "Methods are evaluated.", "papers": ["paper_001"]}]

    summary = DomainSynthesizerAgent(
        input_dir=root,
        llm_client=StaticLLMClient(response),
    ).run()

    out = analysis_dir(root) / "domain_synthesis.json"
    assert summary["written_count"] == 1
    assert json.loads(out.read_text(encoding="utf-8"))["unknown_evidence_papers"] == []


def test_domain_synthesizer_agent_writes_monitor(monkeypatch, tmp_path):
    patch_evidence_models(monkeypatch)
    root = make_agent_input(tmp_path)
    PaperReaderAgent(input_dir=root, provider="dry-run").run()

    DomainSynthesizerAgent(input_dir=root, provider="dry-run", monitor=RunMonitor(tmp_path / "monitor")).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    summary = json.loads((analysis_dir(root) / "domain_synthesizer_summary.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "domain_synthesis"
    assert status["total"] == 1
    assert summary["monitor_status"].endswith("run_status.json")


def test_agent_cli_parsers_accept_monitor_arguments(tmp_path):
    paper_args = build_paper_parser().parse_args([
        "--input-dir",
        str(tmp_path / "agent_inputs"),
        "--provider",
        "deepseek",
        "--model",
        "deepseek-v4-flash",
        "--base-url",
        "https://api.deepseek.com",
        "--results-dir",
        str(tmp_path / "results"),
        "--workers",
        "3",
        "--input-mode",
        "full-text",
        "--max-chunks-per-paper",
        "6",
        "--max-chunk-chars",
        "1200",
        "--monitor-dir",
        str(tmp_path / "monitor"),
    ])
    domain_args = build_domain_parser().parse_args([
        "--input-dir",
        str(tmp_path / "agent_inputs"),
        "--results-dir",
        str(tmp_path / "results"),
        "--no-monitor",
    ])

    assert paper_args.monitor_dir.endswith("monitor")
    assert paper_args.provider == "deepseek"
    assert paper_args.model == "deepseek-v4-flash"
    assert paper_args.base_url == "https://api.deepseek.com"
    assert paper_args.results_dir.endswith("results")
    assert paper_args.workers == 3
    assert paper_args.input_mode == "full-text"
    assert paper_args.max_chunks_per_paper == 6
    assert paper_args.max_chunk_chars == 1200
    assert paper_args.no_monitor is False
    assert domain_args.results_dir.endswith("results")
    assert domain_args.no_monitor is True
