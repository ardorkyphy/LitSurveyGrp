# -*- coding: utf-8 -*-

from litsurveygrp.__main__ import build_parser


def test_cli_survey_arguments_are_core_workflow_focused():
    parser = build_parser()
    args = parser.parse_args([
        "survey",
        "--out",
        r"D:\runs\ai_neuro",
        "--query",
        "AI in neuroscience",
        "--limit",
        "200",
        "--top-papers",
        "30",
        "--top-domains",
        "8",
        "--per-domain",
        "20",
        "--download-workers",
        "4",
        "--agent-provider",
        "deepseek",
        "--agent-model",
        "deepseek-v4-flash",
        "--agent-base-url",
        "https://api.deepseek.com",
        "--enrichment-workers",
        "4",
        "--classification-workers",
        "4",
        "--domain-rules",
        "rules.json",
        "--analyze-references",
        "--max-references-per-paper",
        "40",
        "--max-total-references",
        "400",
        "--reference-relevance-threshold",
        "0.35",
        "--max-reference-downloads",
        "5",
        "--min-reference-value-score",
        "0.55",
        "--require-reference-doi",
        "--reference-query",
        "foundation papers",
        "--reference-sources",
        "openalex",
        "crossref",
        "--title",
        "AI Neuroscience Survey",
    ])

    assert args.command == "survey"
    assert args.out.endswith("ai_neuro")
    assert args.query == "AI in neuroscience"
    assert args.limit == 200
    assert args.top_papers == 30
    assert args.top_domains == 8
    assert args.per_domain == 20
    assert args.download_workers == 4
    assert args.agent_provider == "deepseek"
    assert args.agent_model == "deepseek-v4-flash"
    assert args.agent_base_url == "https://api.deepseek.com"
    assert args.enrichment_workers == 4
    assert args.classification_workers == 4
    assert args.domain_rules == "rules.json"
    assert args.analyze_references is True
    assert args.max_references_per_paper == 40
    assert args.max_total_references == 400
    assert args.reference_relevance_threshold == 0.35
    assert args.max_reference_downloads == 5
    assert args.min_reference_value_score == 0.55
    assert args.require_reference_doi is True
    assert args.reference_query == "foundation papers"
    assert args.reference_sources == ["openalex", "crossref"]
    assert args.title == "AI Neuroscience Survey"


def test_cli_report_arguments():
    parser = build_parser()
    args = parser.parse_args([
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


def test_cli_monitor_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "monitor",
        "--results-dir",
        r"D:\中文路径\results",
        "--open",
        "--once",
        "--interval",
        "2",
    ])

    assert args.command == "monitor"
    assert args.results_dir.endswith("results")
    assert args.open is True
    assert args.once is True
    assert args.interval == 2


def test_cli_clean_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "clean",
        "--target",
        "papers",
        "--target",
        "results",
        "--dry-run",
    ])

    assert args.command == "clean"
    assert args.target == ["papers", "results"]
    assert args.dry_run is True


def test_cli_list_journals_arguments():
    parser = build_parser()
    args = parser.parse_args(["list-journals", "--group", "ccf-a-journal"])

    assert args.command == "list-journals"
    assert args.group == "ccf-a-journal"


def test_stage_commands_are_public_cli():
    parser = build_parser()

    download = parser.parse_args([
        "download-pdfs",
        "--manifest",
        "classified.json",
        "--papers-dir",
        "papers",
        "--results-dir",
        "results",
        "--top",
        "12",
        "--min-value-score",
        "0.5",
        "--download-workers",
        "3",
        "--require-doi",
        "--include-existing",
    ])
    assert download.command == "download-pdfs"
    assert download.manifest == "classified.json"
    assert download.papers_dir == "papers"
    assert download.results_dir == "results"
    assert download.top == 12
    assert download.min_value_score == 0.5
    assert download.download_workers == 3
    assert download.require_doi is True
    assert download.include_existing is True

    agent_input = parser.parse_args([
        "prepare-agent-input",
        "--manifest",
        "pdf_manifest.json",
        "--out-dir",
        "agent_inputs",
        "--top-domains",
        "5",
        "--per-domain",
        "8",
        "--copy-pdfs",
        "--extract-pdf-text",
        "--project-name",
        "demo",
    ])
    assert agent_input.command == "prepare-agent-input"
    assert agent_input.manifest == "pdf_manifest.json"
    assert agent_input.out_dir == "agent_inputs"
    assert agent_input.top_domains == 5
    assert agent_input.per_domain == 8
    assert agent_input.copy_pdfs is True
    assert agent_input.extract_pdf_text is True
    assert agent_input.project_name == "demo"

    enrich = parser.parse_args([
        "enrich-metadata",
        "--manifest",
        "article_manifest.json",
        "--sources",
        "openalex",
        "crossref",
        "--out",
        "enriched.json",
        "--workers",
        "4",
    ])
    assert enrich.command == "enrich-metadata"
    assert enrich.sources == ["openalex", "crossref"]
    assert enrich.out == "enriched.json"
    assert enrich.workers == 4

    classify = parser.parse_args([
        "classify-papers",
        "--manifest",
        "enriched.json",
        "--out-dir",
        "results",
        "--organize-dir",
        "papers",
        "--domain-rules",
        "rules.json",
        "--classification-workers",
        "2",
    ])
    assert classify.command == "classify-papers"
    assert classify.out_dir == "results"
    assert classify.organize_dir == "papers"
    assert classify.domain_rules == "rules.json"
    assert classify.classification_workers == 2

    stats = parser.parse_args(["stats", "--manifest", "classified.json", "--out-dir", "stats", "--top", "10"])
    assert stats.command == "stats"
    assert stats.manifest == "classified.json"
    assert stats.out_dir == "stats"
    assert stats.top == 10

    visualize = parser.parse_args(["visualize", "--manifest", "classified.json", "--out-dir", "viz", "--top", "9"])
    assert visualize.command == "visualize"
    assert visualize.manifest == "classified.json"
    assert visualize.out_dir == "viz"
    assert visualize.top == 9
