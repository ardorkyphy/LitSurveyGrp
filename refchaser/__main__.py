import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    download = subparsers.add_parser("download-nature-aging", help="download Nature Aging papers")
    download.add_argument("--year", type=int)
    add_article_filter_arguments(download)
    download.add_argument("--to", required=True, help="directory to save papers and reports")
    download.add_argument("--results-dir", help="directory to save manifests and reports")
    download.add_argument("--limit", type=int)
    download.add_argument("--download-timeout", type=int, default=15, help="network timeout in seconds for metadata and PDF requests")
    download.add_argument("--pdf-only-candidates", action="store_true", help="skip records unless the provider supplied a direct PDF URL")
    download.add_argument("--dry-run", action="store_true")

    download_journals = subparsers.add_parser("download-journals", help="download papers from configured journals")
    download_journals.add_argument("--journal", action="append", required=True, help="journal key or custom spec, e.g. nature-aging or 'Nature Aging=nataging:s43587-'")
    download_journals.add_argument("--year", type=int)
    add_article_filter_arguments(download_journals)
    download_journals.add_argument("--to", required=True, help="directory to save papers and reports")
    download_journals.add_argument("--results-dir", help="directory to save manifests and reports")
    download_journals.add_argument("--limit", type=int, help="maximum number of complete PDFs across all journals")
    download_journals.add_argument("--per-journal-limit", type=int, help="maximum discovered articles per journal")
    download_journals.add_argument("--download-timeout", type=int, default=15, help="network timeout in seconds for metadata and PDF requests")
    download_journals.add_argument("--pdf-only-candidates", action="store_true", help="skip records unless the provider supplied a direct PDF URL")
    download_journals.add_argument("--dry-run", action="store_true")

    list_journals = subparsers.add_parser("list-journals", help="list built-in journal catalog entries")
    list_journals.add_argument("--group", help="filter by journal group, e.g. ccf-a-journal")

    classify = subparsers.add_parser("classify-papers", help="classify downloaded papers")
    classify.add_argument("--manifest", required=True)
    classify.add_argument("--move", action="store_true", help="move PDFs instead of copying")
    classify.add_argument("--out-dir", help="directory to save classified_manifest.json and basic_stats.json")
    classify.add_argument("--organize-dir", help="directory where PDFs should be organized into classified folders")
    classify.add_argument("--sentence-model", default="allenai-specter", help="SPECTER sentence-transformers model name")

    export_ris = subparsers.add_parser("export-ris", help="export manifest or cited references to RIS")
    export_ris.add_argument("--manifest", required=True)
    export_ris.add_argument("--out")
    export_ris.add_argument("--references", action="store_true", help="export relevant cited references instead of source papers")
    export_ris.add_argument("--max-records", type=int, help="maximum number of cited/reference records to export")
    export_ris.add_argument("--relevance-percent", type=float, help="minimum reference relevance score as a percentage, e.g. 12")
    export_ris.add_argument("--require-doi", action="store_true", help="export cited/reference records only when DOI is available")

    extract_refs = subparsers.add_parser("extract-references", help="extract cited references from downloaded PDFs")
    extract_refs.add_argument("--manifest", required=True)
    extract_refs.add_argument("--max-references", type=int)

    analyze_refs = subparsers.add_parser("analyze-references", help="build and rank a cited-reference paper pool")
    analyze_refs.add_argument("--manifest", required=True)
    add_reference_analysis_arguments(analyze_refs)

    enrich = subparsers.add_parser("enrich-metadata", help="enrich paper metadata from open scholarly APIs")
    enrich.add_argument("--manifest", required=True)
    enrich.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    enrich.add_argument("--out")
    enrich.add_argument("--timeout", type=int, default=15)
    enrich.add_argument("--request-interval", type=float, default=1.0, help="minimum seconds between metadata API calls")

    stats = subparsers.add_parser("stats", help="write research-oriented statistics from a manifest")
    stats.add_argument("--manifest", required=True)
    stats.add_argument("--out-dir")
    stats.add_argument("--top", type=int, default=20)

    visualize = subparsers.add_parser("visualize", help="write an offline research dashboard HTML")
    visualize.add_argument("--manifest", required=True)
    visualize.add_argument("--out-dir")
    visualize.add_argument("--top", type=int, default=15)

    pipeline = subparsers.add_parser("run-survey", help="run download, enrichment, classification, stats, and visualization")
    pipeline.add_argument("--journal", action="append", help="journal key or custom spec; defaults to nature-aging")
    pipeline.add_argument("--query", default="", help="OpenAlex full-work search query when no journal is specified")
    pipeline.add_argument("--year", type=int)
    add_article_filter_arguments(pipeline)
    pipeline.add_argument("--limit", type=int, help="maximum number of complete PDFs across all journals")
    pipeline.add_argument("--per-journal-limit", type=int, help="maximum discovered articles per journal")
    pipeline.add_argument("--papers-dir", default="papers", help="directory to save PDFs and classified folders")
    pipeline.add_argument("--results-dir", default="results", help="directory to save manifests, reports, stats, and visualization")
    pipeline.add_argument("--download-timeout", type=int, default=15, help="network timeout in seconds for metadata and PDF requests")
    pipeline.add_argument("--pdf-only-candidates", action="store_true", help="skip records unless the provider supplied a direct PDF URL")
    pipeline.add_argument("--dry-run", action="store_true")
    pipeline.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    pipeline.add_argument("--metadata-timeout", type=int, default=15)
    pipeline.add_argument("--request-interval", type=float, default=1.0, help="minimum seconds between metadata API calls")
    pipeline.add_argument("--sentence-model", default="allenai-specter", help="SPECTER sentence-transformers model name")
    pipeline.add_argument("--top", type=int, default=20)
    pipeline.add_argument("--move", action="store_true", help="move PDFs into classified folders instead of copying")
    pipeline.add_argument("--clean-existing", action="store_true", help="remove existing papers/results directories before running")
    pipeline.add_argument("--skip-enrichment", action="store_true")
    pipeline.add_argument("--skip-classification", action="store_true")
    pipeline.add_argument("--skip-stats", action="store_true")
    pipeline.add_argument("--skip-visualization", action="store_true")
    pipeline.add_argument("--analyze-references", action="store_true")
    add_reference_analysis_arguments(pipeline)

    return parser


def add_article_filter_arguments(parser):
    parser.add_argument("--from-year", type=int, help="earliest publication year to keep")
    parser.add_argument("--to-year", type=int, help="latest publication year to keep")
    parser.add_argument("--keyword", action="append", help="required keyword; all provided keywords must match title/abstract/type")
    parser.add_argument("--article-type", action="append", help="article type to keep, e.g. Article or Review")
    parser.add_argument("--min-citations", type=int, help="minimum citation count to keep before download")
    parser.add_argument("--author", action="append", help="author name fragment to keep")
    parser.add_argument("--institution", action="append", help="institution name fragment to keep")
    parser.add_argument(
        "--filter-sources",
        nargs="+",
        choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"],
        help="metadata sources used only for citation-threshold prefiltering",
    )


def add_reference_analysis_arguments(parser):
    parser.add_argument("--out-dir", help="directory to save reference analysis outputs")
    parser.add_argument("--max-references-per-paper", type=int, default=50)
    parser.add_argument("--max-total-references", type=int, default=1000)
    parser.add_argument("--reference-relevance-threshold", type=float, default=0.30)
    parser.add_argument("--max-reference-downloads", type=int, default=0)
    parser.add_argument("--min-reference-value-score", type=float, default=0.45)
    parser.add_argument("--require-reference-doi", action="store_true")
    parser.add_argument("--reference-query", default="")
    parser.add_argument("--reference-sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "download-nature-aging":
        from refchaser.multi_journal_downloader import run_nature_aging_from_args
        return run_nature_aging_from_args(args)
    if args.command == "download-journals":
        from refchaser.multi_journal_downloader import run_from_args
        return run_from_args(args)
    if args.command == "list-journals":
        from refchaser.multi_journal_downloader import run_list_from_args
        return run_list_from_args(args)
    if args.command == "classify-papers":
        from refchaser.paper_classifier import run_from_args
        return run_from_args(args)
    if args.command == "export-ris":
        from refchaser.citation_exporter import run_from_args
        return run_from_args(args)
    if args.command == "extract-references":
        from refchaser.reference_extractor import run_from_args
        return run_from_args(args)
    if args.command == "analyze-references":
        from refchaser.reference_analysis import run_from_args
        return run_from_args(args)
    if args.command == "enrich-metadata":
        from refchaser.enrichment.metadata_enrichment import run_from_args
        return run_from_args(args)
    if args.command == "stats":
        from refchaser.research_stats import run_from_args
        return run_from_args(args)
    if args.command == "visualize":
        from refchaser.visualization import run_from_args
        return run_from_args(args)
    if args.command == "run-survey":
        from refchaser.pipeline import run_from_args
        return run_from_args(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
