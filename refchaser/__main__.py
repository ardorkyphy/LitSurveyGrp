import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    download = subparsers.add_parser("download-nature-aging", help="download Nature Aging papers")
    download.add_argument("--year", type=int)
    download.add_argument("--to", required=True, help="directory to save papers and reports")
    download.add_argument("--results-dir", help="directory to save manifests and reports")
    download.add_argument("--limit", type=int)
    download.add_argument("--download-timeout", type=int, default=15, help="network timeout in seconds for metadata and PDF requests")
    download.add_argument("--pdf-only-candidates", action="store_true", help="skip records unless the provider supplied a direct PDF URL")
    download.add_argument("--dry-run", action="store_true")

    download_journals = subparsers.add_parser("download-journals", help="download papers from configured journals")
    download_journals.add_argument("--journal", action="append", required=True, help="journal key or custom spec, e.g. nature-aging or 'Nature Aging=nataging:s43587-'")
    download_journals.add_argument("--year", type=int)
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

    return parser


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
    if args.command == "enrich-metadata":
        from refchaser.enrichment.metadata_enrichment import run_from_args
        return run_from_args(args)
    if args.command == "stats":
        from refchaser.research_stats import run_from_args
        return run_from_args(args)
    if args.command == "visualize":
        from refchaser.visualization import run_from_args
        return run_from_args(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
