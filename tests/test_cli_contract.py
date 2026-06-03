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
        "--move",
    ])

    assert args.command == "classify-papers"
    assert args.manifest.endswith("article_manifest.json")
    assert args.out_dir.endswith("results")
    assert args.organize_dir.endswith("papers")
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
