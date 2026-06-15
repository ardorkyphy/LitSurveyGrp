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
        "--pdfs-per-domain",
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
        "--agent-workers",
        "3",
        "--agent-input-mode",
        "evidence-chunks",
        "--agent-max-chunks-per-paper",
        "9",
        "--agent-max-chunk-chars",
        "1800",
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
    assert args.pdfs_per_domain == 30
    assert args.top_domains == 8
    assert args.per_domain == 20
    assert args.download_workers == 4
    assert args.agent_provider == "deepseek"
    assert args.agent_model == "deepseek-v4-flash"
    assert args.agent_base_url == "https://api.deepseek.com"
    assert args.agent_workers == 3
    assert args.agent_input_mode == "evidence-chunks"
    assert args.agent_max_chunks_per_paper == 9
    assert args.agent_max_chunk_chars == 1800
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


def test_cli_survey_customer_friendly_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "survey",
        "--out",
        "run",
        "--query",
        "Causal Discovery",
        "--preset",
        "full",
        "--pdfs",
        "30",
        "--domains",
        "8",
        "--papers-per-domain",
        "30",
        "--model-provider",
        "openai",
        "--model",
        "gpt-4.1",
        "--workers",
        "4",
    ])

    assert args.preset == "full"
    assert args.pdfs == 30
    assert args.domains == 8
    assert args.papers_per_domain == 30
    assert args.model_provider == "openai"
    assert args.model == "gpt-4.1"
    assert args.workers == 4


def test_cli_survey_stage_control_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "survey",
        "--out",
        "run",
        "--skip-stage",
        "stats",
        "--skip-stage",
        "visualization",
        "--stage-mode",
        "pdf_download=top-ranked",
        "--stage-mode",
        "paper_agents=disabled",
    ])

    assert args.skip_stage == ["stats", "visualization"]
    assert args.stage_mode == ["pdf_download=top-ranked", "paper_agents=disabled"]


def test_cli_fetch_pdf_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "fetch-pdf",
        "--out",
        "pdf_run",
        "--title",
        "A precise paper title",
        "--limit",
        "8",
        "--top",
        "2",
        "--sources",
        "openalex",
        "crossref",
        "--download-workers",
        "3",
        "--require-doi",
    ])

    assert args.command == "fetch-pdf"
    assert args.out == "pdf_run"
    assert args.title == "A precise paper title"
    assert args.limit == 8
    assert args.top == 2
    assert args.sources == ["openalex", "crossref"]
    assert args.download_workers == 3
    assert args.require_doi is True


def test_cli_analyze_pdf_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "analyze-pdf",
        "--pdf",
        "paper.pdf",
        "--out",
        "single",
        "--title",
        "Single Paper",
        "--model-provider",
        "deepseek",
        "--model",
        "deepseek-v4-flash",
        "--agent-cache-dir",
        "cache",
        "--copy-pdf",
        "--overwrite",
    ])

    assert args.command == "analyze-pdf"
    assert args.pdf == "paper.pdf"
    assert args.out == "single"
    assert args.title == "Single Paper"
    assert args.model_provider == "deepseek"
    assert args.model == "deepseek-v4-flash"
    assert args.agent_cache_dir == "cache"
    assert args.agent_input_mode == "full-text"
    assert args.copy_pdf is True
    assert args.overwrite is True


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
        "--dir",
        r"D:\中文路径\reports\analysis\data",
        "--open",
        "--once",
        "--interval",
        "2",
    ])

    assert args.command == "monitor"
    assert args.results_dir.endswith("data")
    assert args.open is True
    assert args.once is True
    assert args.interval == 2


def test_cli_top_level_help_hides_internal_stage_commands(capsys):
    parser = build_parser()

    parser.print_help()
    help_text = capsys.readouterr().out

    assert "download-pdfs" not in help_text
    assert "prepare-agent-input" not in help_text
    assert "survey" in help_text
    assert "fetch-pdf" in help_text
    assert "analyze-pdf" in help_text
    assert "monitor" in help_text


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
        "--per-domain",
        "2",
        "--require-doi",
        "--include-existing",
        "--monitor-dir",
        "reports/analysis/data",
    ])
    assert download.command == "download-pdfs"
    assert download.manifest == "classified.json"
    assert download.papers_dir == "papers"
    assert download.results_dir == "results"
    assert download.top == 12
    assert download.min_value_score == 0.5
    assert download.download_workers == 3
    assert download.per_domain == 2
    assert download.require_doi is True
    assert download.include_existing is True
    assert download.monitor_dir == "reports/analysis/data"

    agent_input = parser.parse_args([
        "prepare-agent-input",
        "--manifest",
        "pdf_manifest.json",
        "--out-dir",
        "data",
        "--papers-dir",
        "papers",
        "--results-dir",
        "results",
        "--top-domains",
        "5",
        "--per-domain",
        "8",
        "--selection",
        "top-downloaded-pdfs",
        "--top-papers",
        "30",
        "--copy-pdfs",
        "--extract-pdf-text",
        "--project-name",
        "demo",
    ])
    assert agent_input.command == "prepare-agent-input"
    assert agent_input.manifest == "pdf_manifest.json"
    assert agent_input.out_dir == "data"
    assert agent_input.papers_dir == "papers"
    assert agent_input.results_dir == "results"
    assert agent_input.top_domains == 5
    assert agent_input.per_domain == 8
    assert agent_input.selection == "top-downloaded-pdfs"
    assert agent_input.top_papers == 30
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
def test_cli_pdf_download_defaults_to_parallel_workers():
    parser = build_parser()

    survey = parser.parse_args(["survey", "--out", "run", "--query", "causal discovery"])
    download = parser.parse_args(["download-pdfs", "--manifest", "classified.json", "--papers-dir", "papers"])

    assert survey.download_workers is None
    assert survey.preset == "balanced"
    assert download.download_workers == 8
