import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", metavar="{survey,fetch-pdf,analyze-pdf,monitor,clean,list-journals}")

    survey = subparsers.add_parser("survey", help="run the metadata-to-agent-report workflow")
    survey.add_argument("--out", required=True, help="run output root; papers, results, and reports are written under it")
    survey.add_argument("--query", default="", help="research keyword or topic, e.g. Causal Discovery")
    survey.add_argument("--journal", action="append", help=argparse.SUPPRESS)
    survey.add_argument("--preset", default="balanced", choices=["fast", "balanced", "full", "metadata"], help="workflow preset for common use")
    survey.add_argument("--pdfs", type=int, help="PDFs to download per selected domain; 0 skips PDF download")
    survey.add_argument("--domains", type=int, help="number of domains to analyze")
    survey.add_argument("--papers-per-domain", type=int, help="papers to package for each analyzed domain")
    survey.add_argument("--model-provider", dest="model_provider", choices=["dry-run", "openai", "deepseek"], help="LLM provider for agent analysis")
    survey.add_argument("--model", dest="model", help="LLM model name")
    survey.add_argument("--workers", type=int, help="shared default for PDF and agent workers")
    add_article_filter_arguments(survey)
    survey.add_argument("--limit", type=int, help="maximum discovered records")
    survey.add_argument("--per-journal-limit", type=int, help=argparse.SUPPRESS)
    survey.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"], help=argparse.SUPPRESS)
    survey.add_argument("--request-interval", type=float, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--enrichment-workers", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--classification-workers", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--top-papers", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--pdfs-per-domain", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--top-domains", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--per-domain", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--download-workers", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--download-timeout", type=int, default=15, help=argparse.SUPPRESS)
    survey.add_argument("--min-value-score", type=float, help=argparse.SUPPRESS)
    survey.add_argument("--require-doi", action="store_true", help=argparse.SUPPRESS)
    survey.add_argument("--agent-provider", default=None, choices=["dry-run", "openai", "deepseek"], help=argparse.SUPPRESS)
    survey.add_argument("--agent-model", default=None, help=argparse.SUPPRESS)
    survey.add_argument("--agent-base-url", default="", help=argparse.SUPPRESS)
    survey.add_argument("--agent-cache-dir", help=argparse.SUPPRESS)
    survey.add_argument("--agent-workers", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--agent-input-mode", default=None, choices=["evidence-chunks", "full-text"], help=argparse.SUPPRESS)
    survey.add_argument("--agent-max-chunks-per-paper", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--agent-max-chunk-chars", type=int, default=None, help=argparse.SUPPRESS)
    survey.add_argument("--skip-agents", action="store_true", help="prepare agent inputs but skip LLM analysis")
    survey.add_argument("--no-extract-pdf-text", action="store_true", help="do not extract downloaded PDF text for agents")
    survey.add_argument("--skip-stage", action="append", default=[], help=argparse.SUPPRESS)
    survey.add_argument("--stage-mode", action="append", default=[], help=argparse.SUPPRESS)
    survey.add_argument("--max-text-chars", type=int, default=0, help=argparse.SUPPRESS)
    survey.add_argument("--domain-rules", default="", help=argparse.SUPPRESS)
    survey.add_argument("--analyze-references", action="store_true", help="also analyze cited references")
    survey.add_argument("--max-references-per-paper", type=int, default=50, help=argparse.SUPPRESS)
    survey.add_argument("--max-total-references", type=int, default=1000, help=argparse.SUPPRESS)
    survey.add_argument("--reference-relevance-threshold", type=float, default=0.30, help=argparse.SUPPRESS)
    survey.add_argument("--max-reference-downloads", type=int, default=0, help=argparse.SUPPRESS)
    survey.add_argument("--min-reference-value-score", type=float, default=0.45, help=argparse.SUPPRESS)
    survey.add_argument("--require-reference-doi", action="store_true", help=argparse.SUPPRESS)
    survey.add_argument("--reference-query", default="", help=argparse.SUPPRESS)
    survey.add_argument("--reference-sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"], help=argparse.SUPPRESS)
    survey.add_argument("--title", default="", help="final report title")
    survey.add_argument("--clean-existing", action="store_true", help="remove existing papers/results directories before running")

    fetch_pdf = subparsers.add_parser("fetch-pdf", help="find papers by title or keyword query and download PDFs")
    fetch_pdf.add_argument("--out", required=True, help="run output root; papers and reports are written under it")
    fetch_pdf.add_argument("--title", default="", help="paper title to search for; defaults to downloading the best match")
    fetch_pdf.add_argument("--query", default="", help="keyword query to search for")
    fetch_pdf.add_argument("--limit", type=int, default=5, help="maximum candidate papers to discover")
    fetch_pdf.add_argument("--top", type=int, default=1, help="candidate PDFs to attempt after ranking or title matching")
    fetch_pdf.add_argument("--sources", nargs="+", default=None, choices=["openalex", "crossref", "europe-pmc"], help="metadata search sources")
    fetch_pdf.add_argument("--download-workers", type=int, default=8, help="parallel PDF download workers")
    fetch_pdf.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    fetch_pdf.add_argument("--require-doi", action="store_true", help="skip candidates without DOI")
    fetch_pdf.add_argument("--include-existing", action="store_true", help="include already downloaded PDFs in the selected set")
    fetch_pdf.add_argument("--monitor-dir", help=argparse.SUPPRESS)
    fetch_pdf.add_argument("--no-monitor", action="store_true", help=argparse.SUPPRESS)

    analyze_pdf = subparsers.add_parser("analyze-pdf", help="analyze one local PDF with the paper agent")
    analyze_pdf.add_argument("--pdf", required=True, help="local PDF path")
    analyze_pdf.add_argument("--out", required=True, help="run output root; package, analysis, and report are written under it")
    analyze_pdf.add_argument("--title", default="", help="paper title; defaults to the PDF filename")
    analyze_pdf.add_argument("--doi", default="", help="paper DOI")
    analyze_pdf.add_argument("--journal", default="", help="paper journal or venue")
    analyze_pdf.add_argument("--publish-date", default="", help="paper publication date or year")
    analyze_pdf.add_argument("--abstract", default="", help="paper abstract, if known")
    analyze_pdf.add_argument("--model-provider", dest="model_provider", default="dry-run", choices=["dry-run", "openai", "deepseek"], help="LLM provider")
    analyze_pdf.add_argument("--model", default="", help="LLM model name")
    analyze_pdf.add_argument("--agent-base-url", default="", help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--agent-cache-dir", help="directory for LLM response cache")
    analyze_pdf.add_argument("--agent-input-mode", default="full-text", choices=["evidence-chunks", "full-text"], help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--agent-max-chunks-per-paper", type=int, default=12, help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--agent-max-chunk-chars", type=int, default=2200, help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--max-text-chars", type=int, default=0, help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--copy-pdf", action="store_true", help="copy the source PDF into the output papers directory")
    analyze_pdf.add_argument("--overwrite", action="store_true", help="overwrite existing agent outputs")
    analyze_pdf.add_argument("--monitor-dir", help=argparse.SUPPRESS)
    analyze_pdf.add_argument("--no-monitor", action="store_true", help=argparse.SUPPRESS)

    report = subparsers.add_parser("report", help=argparse.SUPPRESS)
    report.add_argument("--results-dir", required=True)
    report.add_argument("--reports-dir")
    report.add_argument("--agent-dir")
    report.add_argument("--out")
    report.add_argument("--html-out")
    report.add_argument("--title", default="")
    report.add_argument("--max-domains", type=int, default=10)
    report.add_argument("--max-papers-per-domain", type=int, default=8)
    report.add_argument("--max-recommended-papers", type=int, default=12)

    download_pdfs = subparsers.add_parser("download-pdfs", help=argparse.SUPPRESS)
    download_pdfs.add_argument("--manifest", required=True)
    download_pdfs.add_argument("--papers-dir", required=True)
    download_pdfs.add_argument("--results-dir")
    download_pdfs.add_argument("--top", type=int, default=20)
    download_pdfs.add_argument("--per-domain", type=int, default=0)
    download_pdfs.add_argument("--min-value-score", type=float)
    download_pdfs.add_argument("--download-workers", type=int, default=8)
    download_pdfs.add_argument("--timeout", type=int, default=15)
    download_pdfs.add_argument("--require-doi", action="store_true")
    download_pdfs.add_argument("--include-existing", action="store_true")
    download_pdfs.add_argument("--no-retry-oa-resolution", action="store_true")
    download_pdfs.add_argument("--out-manifest-name", default="pdf_downloaded_manifest.json")
    download_pdfs.add_argument("--monitor-dir")

    prepare_agent_input = subparsers.add_parser("prepare-agent-input", help=argparse.SUPPRESS)
    prepare_agent_input.add_argument("--manifest", required=True)
    prepare_agent_input.add_argument("--out-dir", required=True)
    prepare_agent_input.add_argument("--papers-dir")
    prepare_agent_input.add_argument("--results-dir")
    prepare_agent_input.add_argument("--reports-dir")
    prepare_agent_input.add_argument("--top-domains", type=int, default=10)
    prepare_agent_input.add_argument("--per-domain", type=int, default=30)
    prepare_agent_input.add_argument("--selection", default="domains", choices=["domains", "top-downloaded-pdfs"])
    prepare_agent_input.add_argument("--top-papers", type=int, default=30)
    prepare_agent_input.add_argument("--copy-pdfs", action="store_true")
    prepare_agent_input.add_argument("--extract-pdf-text", action="store_true")
    prepare_agent_input.add_argument("--max-text-chars", type=int, default=0, help="maximum extracted PDF text chars to keep; 0 keeps full text")
    prepare_agent_input.add_argument("--project-name", default="")
    prepare_agent_input.add_argument("--no-monitor", action="store_true")
    prepare_agent_input.add_argument("--monitor-dir")

    enrich_metadata = subparsers.add_parser("enrich-metadata", help=argparse.SUPPRESS)
    enrich_metadata.add_argument("--manifest", required=True)
    enrich_metadata.add_argument("--sources", nargs="+", choices=["openalex", "semantic-scholar", "europe-pmc", "crossref"])
    enrich_metadata.add_argument("--out")
    enrich_metadata.add_argument("--timeout", type=int, default=15)
    enrich_metadata.add_argument("--request-interval", type=float, default=1.0)
    enrich_metadata.add_argument("--workers", type=int, default=1)

    classify_papers = subparsers.add_parser("classify-papers", help=argparse.SUPPRESS)
    classify_papers.add_argument("--manifest", required=True)
    classify_papers.add_argument("--out-dir")
    classify_papers.add_argument("--organize-dir")
    classify_papers.add_argument("--move", action="store_true")
    classify_papers.add_argument("--sentence-model")
    classify_papers.add_argument("--domain-rules", default="")
    classify_papers.add_argument("--classification-workers", type=int, default=1)

    stats = subparsers.add_parser("stats", help=argparse.SUPPRESS)
    stats.add_argument("--manifest", required=True)
    stats.add_argument("--out-dir")
    stats.add_argument("--top", type=int, default=20)

    visualize = subparsers.add_parser("visualize", help=argparse.SUPPRESS)
    visualize.add_argument("--manifest", required=True)
    visualize.add_argument("--out-dir")
    visualize.add_argument("--top", type=int, default=15)

    monitor = subparsers.add_parser("monitor", help="open or watch the live run monitor")
    monitor.add_argument("--dir", dest="results_dir", default="reports", help="directory containing run_monitor.html and run_status.json")
    monitor.add_argument("--results-dir", dest="results_dir", help=argparse.SUPPRESS)
    monitor.add_argument("--open", action="store_true", help="open run_monitor.html in the default browser")
    monitor.add_argument("--watch", action="store_true", help="print run status repeatedly in the terminal")
    monitor.add_argument("--once", action="store_true", help="print one terminal status line and exit")
    monitor.add_argument("--interval", type=int, default=5, help="seconds between terminal watch updates")

    clean = subparsers.add_parser("clean", help="remove generated papers/results/reports outputs")
    clean.add_argument("--target", action="append", help="relative generated directory to remove; defaults to papers, results, and reports")
    clean.add_argument("--dry-run", action="store_true", help="show cleanup targets without deleting")

    list_journals = subparsers.add_parser("list-journals", help="list built-in journal catalog entries")
    list_journals.add_argument("--group", help="filter by journal group, e.g. ccf-a-journal")

    hide_suppressed_subcommands(subparsers)
    return parser


def hide_suppressed_subcommands(subparsers) -> None:
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions
        if action.help != argparse.SUPPRESS
    ]


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
    if args.command == "fetch-pdf":
        from litsurveygrp.title_pdf_fetch import run_from_args
        return run_from_args(args)
    if args.command == "analyze-pdf":
        from litsurveygrp.single_paper_analysis import run_from_args
        return run_from_args(args)
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
