# -*- coding: utf-8 -*-

from refchaser.__main__ import build_parser


def test_cli_has_mvp_subcommands():
    parser = build_parser()
    args = parser.parse_args([
        "download-nature-aging",
        "--to",
        r"D:\中文路径\papers",
        "--results-dir",
        r"D:\中文路径\results",
        "--year",
        "2026",
        "--limit",
        "3",
    ])

    assert args.command == "download-nature-aging"
    assert args.to == r"D:\中文路径\papers"
    assert args.results_dir == r"D:\中文路径\results"
    assert args.year == 2026
    assert args.limit == 3


def test_cli_classify_papers_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "classify-papers",
        "--manifest",
        r"D:\results\article_manifest.json",
        "--out-dir",
        r"D:\results",
        "--organize-dir",
        r"D:\papers",
        "--sentence-model",
        "allenai-specter",
        "--move",
    ])

    assert args.command == "classify-papers"
    assert args.manifest.endswith("article_manifest.json")
    assert args.out_dir.endswith("results")
    assert args.organize_dir.endswith("papers")
    assert args.sentence_model == "allenai-specter"
    assert args.move is True


def test_cli_export_ris_arguments():
    parser = build_parser()
    args = parser.parse_args(
        [
            "export-ris",
            "--manifest",
            r"D:\papers\classified_manifest.json",
            "--out",
            r"D:\papers\out.ris",
        ]
    )

    assert args.command == "export-ris"
    assert args.manifest.endswith("classified_manifest.json")
    assert args.out.endswith("out.ris")


def test_cli_enrich_metadata_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "enrich-metadata",
        "--manifest",
        r"D:\中文路径\multi_journal_manifest.json",
        "--sources",
        "openalex",
        "crossref",
        "--out",
        r"D:\中文路径\enriched.json",
        "--timeout",
        "9",
        "--request-interval",
        "5",
    ])

    assert args.command == "enrich-metadata"
    assert args.manifest.endswith("multi_journal_manifest.json")
    assert args.sources == ["openalex", "crossref"]
    assert args.out.endswith("enriched.json")
    assert args.timeout == 9
    assert args.request_interval == 5


def test_cli_stats_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "stats",
        "--manifest",
        r"D:\中文路径\enriched_manifest.json",
        "--out-dir",
        r"D:\中文路径\stats",
        "--top",
        "10",
    ])

    assert args.command == "stats"
    assert args.manifest.endswith("enriched_manifest.json")
    assert args.out_dir.endswith("stats")
    assert args.top == 10


def test_cli_visualize_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "visualize",
        "--manifest",
        r"D:\中文路径\enriched_manifest.json",
        "--out-dir",
        r"D:\中文路径\visualization",
        "--top",
        "8",
    ])

    assert args.command == "visualize"
    assert args.manifest.endswith("enriched_manifest.json")
    assert args.out_dir.endswith("visualization")
    assert args.top == 8


def test_cli_run_survey_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "run-survey",
        "--query",
        "LLM causal discovery",
        "--year",
        "2026",
        "--limit",
        "50",
        "--papers-dir",
        r"D:\中文路径\papers",
        "--results-dir",
        r"D:\中文路径\results",
        "--sources",
        "openalex",
        "crossref",
        "--request-interval",
        "1.5",
        "--analyze-references",
        "--max-references-per-paper",
        "30",
        "--max-reference-downloads",
        "5",
        "--clean-existing",
    ])

    assert args.command == "run-survey"
    assert args.query == "LLM causal discovery"
    assert args.journal is None
    assert args.year == 2026
    assert args.limit == 50
    assert args.papers_dir.endswith("papers")
    assert args.results_dir.endswith("results")
    assert args.sources == ["openalex", "crossref"]
    assert args.request_interval == 1.5
    assert args.analyze_references is True
    assert args.max_references_per_paper == 30
    assert args.max_reference_downloads == 5
    assert args.clean_existing is True


def test_cli_analyze_references_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "analyze-references",
        "--manifest",
        r"D:\results\classified_manifest.json",
        "--out-dir",
        r"D:\results\references",
        "--max-references-per-paper",
        "40",
        "--max-total-references",
        "400",
        "--reference-relevance-threshold",
        "0.35",
        "--max-reference-downloads",
        "20",
        "--min-reference-value-score",
        "0.5",
        "--require-reference-doi",
        "--reference-query",
        "immune aging",
        "--reference-sources",
        "openalex",
        "crossref",
    ])

    assert args.command == "analyze-references"
    assert args.manifest.endswith("classified_manifest.json")
    assert args.out_dir.endswith("references")
    assert args.max_references_per_paper == 40
    assert args.max_total_references == 400
    assert args.reference_relevance_threshold == 0.35
    assert args.max_reference_downloads == 20
    assert args.min_reference_value_score == 0.5
    assert args.require_reference_doi is True
    assert args.reference_query == "immune aging"
    assert args.reference_sources == ["openalex", "crossref"]
