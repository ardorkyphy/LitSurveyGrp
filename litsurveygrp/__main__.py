import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    survey = subparsers.add_parser("survey", help="run the metadata-to-agent-report workflow")
    survey.add_argument("--out", required=True, help="run output root; papers, results, and agent_inputs are written under it")
    survey.add_argument("--journal", action="append", help="journal key or custom spec; use --query for general OpenAlex keyword search")
    survey.add_argument("--query", default="", help="OpenAlex full-work search query when no journal is specified")
    add_article_filter_arguments(survey)
    survey.add_argument("--limit", type=int, help="maximum discovered records")
    survey.add_argument("--per-journal-limit", type=int, help="maximum discovered records per journal")
    survey.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    survey.add_argument("--request-interval", type=float, default=1.0, help="minimum seconds between metadata API calls")
    survey.add_argument("--enrichment-workers", type=int, default=1, help="parallel metadata enrichment workers")
    survey.add_argument("--classification-workers", type=int, default=1, help="parallel topic classification workers")
    survey.add_argument("--top-papers", type=int, default=30, help="number of top-ranked papers to download and analyze")
    survey.add_argument("--top-domains", type=int, default=10, help="number of domains to package for agents")
    survey.add_argument("--per-domain", type=int, default=30, help="number of papers per domain package")
    survey.add_argument("--download-workers", type=int, default=4, help="parallel top-PDF download workers")
    survey.add_argument("--download-timeout", type=int, default=15, help="network timeout in seconds")
    survey.add_argument("--min-value-score", type=float, help="minimum research value score required for PDF download")
    survey.add_argument("--require-doi", action="store_true", help="download only records with DOI")
    survey.add_argument("--agent-provider", default="dry-run", choices=["dry-run", "openai", "deepseek"])
    survey.add_argument("--agent-model", default="", help="LLM model; defaults by provider")
    survey.add_argument("--agent-base-url", default="", help="optional DeepSeek chat-completions base URL override")
    survey.add_argument("--agent-cache-dir", help="directory for prompt/response cache")
    survey.add_argument("--skip-agents", action="store_true", help="prepare agent inputs but skip LLM analysis")
    survey.add_argument("--no-extract-pdf-text", action="store_true", help="do not extract downloaded PDF text for agents")
    survey.add_argument("--max-text-chars", type=int, default=60000)
    survey.add_argument("--domain-rules", default="", help="optional user-supplied JSON rules file")
    survey.add_argument("--analyze-references", action="store_true", help="analyze cited references from downloaded Top papers")
    survey.add_argument("--max-references-per-paper", type=int, default=50)
    survey.add_argument("--max-total-references", type=int, default=1000)
    survey.add_argument("--reference-relevance-threshold", type=float, default=0.30)
    survey.add_argument("--max-reference-downloads", type=int, default=0)
    survey.add_argument("--min-reference-value-score", type=float, default=0.45)
    survey.add_argument("--require-reference-doi", action="store_true")
    survey.add_argument("--reference-query", default="")
    survey.add_argument("--reference-sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    survey.add_argument("--title", default="", help="final report title")
    survey.add_argument("--clean-existing", action="store_true", help="remove existing papers/results directories before running")

    report = subparsers.add_parser("report", help="rebuild a final report from existing survey outputs")
    report.add_argument("--results-dir", required=True)
    report.add_argument("--agent-dir")
    report.add_argument("--out")
    report.add_argument("--html-out")
    report.add_argument("--title", default="")
    report.add_argument("--max-domains", type=int, default=10)
    report.add_argument("--max-papers-per-domain", type=int, default=8)
    report.add_argument("--max-recommended-papers", type=int, default=12)

    download_pdfs = subparsers.add_parser("download-pdfs", help="download top-ranked PDFs from an existing manifest")
    download_pdfs.add_argument("--manifest", required=True)
    download_pdfs.add_argument("--papers-dir", required=True)
    download_pdfs.add_argument("--results-dir")
    download_pdfs.add_argument("--top", type=int, default=20)
    download_pdfs.add_argument("--min-value-score", type=float)
    download_pdfs.add_argument("--download-workers", type=int, default=1)
    download_pdfs.add_argument("--timeout", type=int, default=15)
    download_pdfs.add_argument("--require-doi", action="store_true")
    download_pdfs.add_argument("--include-existing", action="store_true")
    download_pdfs.add_argument("--no-retry-oa-resolution", action="store_true")
    download_pdfs.add_argument("--out-manifest-name", default="pdf_downloaded_manifest.json")

    prepare_agent_input = subparsers.add_parser("prepare-agent-input", help="prepare per-domain inputs for research agents")
    prepare_agent_input.add_argument("--manifest", required=True)
    prepare_agent_input.add_argument("--out-dir", required=True)
    prepare_agent_input.add_argument("--top-domains", type=int, default=10)
    prepare_agent_input.add_argument("--per-domain", type=int, default=30)
    prepare_agent_input.add_argument("--copy-pdfs", action="store_true")
    prepare_agent_input.add_argument("--extract-pdf-text", action="store_true")
    prepare_agent_input.add_argument("--max-text-chars", type=int, default=60000)
    prepare_agent_input.add_argument("--project-name", default="")
    prepare_agent_input.add_argument("--no-monitor", action="store_true")
    prepare_agent_input.add_argument("--monitor-dir")

    enrich_metadata = subparsers.add_parser("enrich-metadata", help="enrich an existing article manifest with scholarly metadata")
    enrich_metadata.add_argument("--manifest", required=True)
    enrich_metadata.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    enrich_metadata.add_argument("--out")
    enrich_metadata.add_argument("--timeout", type=int, default=15)
    enrich_metadata.add_argument("--request-interval", type=float, default=1.0)
    enrich_metadata.add_argument("--workers", type=int, default=1)

    classify_papers = subparsers.add_parser("classify-papers", help="classify papers into research topics")
    classify_papers.add_argument("--manifest", required=True)
    classify_papers.add_argument("--out-dir")
    classify_papers.add_argument("--organize-dir")
    classify_papers.add_argument("--move", action="store_true")
    classify_papers.add_argument("--sentence-model")
    classify_papers.add_argument("--domain-rules", default="")
    classify_papers.add_argument("--classification-workers", type=int, default=1)

    stats = subparsers.add_parser("stats", help="write research statistics from a classified manifest")
    stats.add_argument("--manifest", required=True)
    stats.add_argument("--out-dir")
    stats.add_argument("--top", type=int, default=20)

    visualize = subparsers.add_parser("visualize", help="write the offline research dashboard")
    visualize.add_argument("--manifest", required=True)
    visualize.add_argument("--out-dir")
    visualize.add_argument("--top", type=int, default=15)

    monitor = subparsers.add_parser("monitor", help="open or watch the live run monitor")
    monitor.add_argument("--results-dir", default="results", help="directory containing run_monitor.html and run_status.json")
    monitor.add_argument("--open", action="store_true", help="open run_monitor.html in the default browser")
    monitor.add_argument("--watch", action="store_true", help="print run status repeatedly in the terminal")
    monitor.add_argument("--once", action="store_true", help="print one terminal status line and exit")
    monitor.add_argument("--interval", type=int, default=5, help="seconds between terminal watch updates")

    clean = subparsers.add_parser("clean", help="remove generated papers/results outputs")
    clean.add_argument("--target", action="append", help="relative generated directory to remove; defaults to papers and results")
    clean.add_argument("--dry-run", action="store_true", help="show cleanup targets without deleting")

    list_journals = subparsers.add_parser("list-journals", help="list built-in journal catalog entries")
    list_journals.add_argument("--group", help="filter by journal group, e.g. ccf-a-journal")

    return parser


def add_article_filter_arguments(parser):
    parser.add_argument("--from-year", type=int, help="earliest publication year to keep")
    parser.add_argument("--to-year", type=int, help="latest publication year to keep")
    parser.add_argument("--keyword", action="append", help="required keyword; all provided keywords must match title/abstract/type")
    parser.add_argument("--article-type", action="append", help="article type to keep, e.g. Article or Review")
    parser.add_argument("--min-citations", type=int, help="minimum citation count to keep before download")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "survey":
        from litsurveygrp.pipeline import run_survey_from_args
        return run_survey_from_args(args)
    if args.command == "report":
        from litsurveygrp.final_report import run_from_args
        return run_from_args(args)
    if args.command == "download-pdfs":
        from litsurveygrp.pdf_download_stage import run_from_args
        return run_from_args(args)
    if args.command == "prepare-agent-input":
        from litsurveygrp.agent_input import run_from_args
        return run_from_args(args)
    if args.command == "enrich-metadata":
        from litsurveygrp.enrichment.metadata_enrichment import run_from_args
        return run_from_args(args)
    if args.command == "classify-papers":
        from litsurveygrp.paper_classifier import run_from_args
        return run_from_args(args)
    if args.command == "stats":
        from litsurveygrp.research_stats import run_from_args
        return run_from_args(args)
    if args.command == "visualize":
        from litsurveygrp.visualization import run_from_args
        return run_from_args(args)
    if args.command == "monitor":
        from litsurveygrp.run_monitor import run_from_args
        return run_from_args(args)
    if args.command == "clean":
        from litsurveygrp.cleanup import run_from_args
        return run_from_args(args)
    if args.command == "list-journals":
        from litsurveygrp.multi_journal_downloader import run_list_from_args
        return run_list_from_args(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
