# -*- coding: utf-8 -*-

import json

from litsurveygrp.agent_input import AgentInputPreparer, run_from_args
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
        out_dir=tmp_path / "agent_inputs",
        top_domains=1,
        per_domain=1,
        project_name="demo",
    ).run()

    assert summary["project_name"] == "demo"
    assert summary["domain_count"] == 1
    package = tmp_path / "agent_inputs" / "domain_001"
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
        out_dir=tmp_path / "agent_inputs",
        top_domains=1,
        per_domain=1,
        monitor=RunMonitor(tmp_path / "monitor"),
    ).run()

    status = json.loads((tmp_path / "monitor" / "run_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "prepare_agent_input"
    assert status["processed"] == 1
    assert "agent input" in status["run_name"].casefold()


def test_prepare_agent_input_cli_adapter(monkeypatch, tmp_path):
    class Args:
        manifest = str(tmp_path / "manifest.json")
        out_dir = str(tmp_path / "agent_inputs")
        project_name = "demo"
        top_domains = 3
        per_domain = 7
        copy_pdfs = True
        extract_pdf_text = False
        max_text_chars = 123
        monitor_dir = str(tmp_path / "monitor")
        no_monitor = False

    captured = {}

    def fake_run(self):
        captured["manifest_path"] = self.manifest_path
        captured["out_dir"] = self.out_dir
        captured["top_domains"] = self.top_domains
        captured["per_domain"] = self.per_domain
        captured["copy_pdfs"] = self.copy_pdfs
        captured["max_text_chars"] = self.max_text_chars
        captured["monitor"] = self.monitor
        return {}

    monkeypatch.setattr(AgentInputPreparer, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["out_dir"].name == "agent_inputs"
    assert captured["top_domains"] == 3
    assert captured["per_domain"] == 7
    assert captured["copy_pdfs"] is True
    assert captured["max_text_chars"] == 123
    assert captured["monitor"].out_dir.name == "monitor"
