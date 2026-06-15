# -*- coding: utf-8 -*-
"""Analyze one local PDF with the paper reader agent."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from agents.paper_reader_agent import PaperReaderAgent
from litsurveygrp.agent_input import safe_pdf_name
from litsurveygrp.analysis_paths import AnalysisLayout, safe_path_name
from litsurveygrp.final_report import markdown_to_html
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.reference_extractor import PdfReferenceExtractor
from litsurveygrp.research_stats import extract_year
from litsurveygrp.run_monitor import RunMonitor


@dataclass
class SinglePaperAnalysisService:
    """Package and analyze a single local PDF."""

    pdf_path: Path
    out_dir: Path
    title: str = ""
    doi: str = ""
    journal: str = ""
    publish_date: str = ""
    abstract: str = ""
    provider: str = "dry-run"
    model: str = ""
    base_url: str = ""
    cache_dir: Path | None = None
    overwrite: bool = False
    input_mode: str = "full-text"
    max_chunks_per_paper: int = 12
    max_chunk_chars: int = 2200
    max_text_chars: int = 0
    copy_pdf: bool = False
    monitor: RunMonitor | None = None
    extractor: PdfReferenceExtractor | None = None
    paper_agent_cls: object = PaperReaderAgent

    def __post_init__(self) -> None:
        self.pdf_path = Path(self.pdf_path)
        self.out_dir = Path(self.out_dir)
        self.cache_dir = Path(self.cache_dir) if self.cache_dir else None
        self.extractor = self.extractor or PdfReferenceExtractor()
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")
        if self.pdf_path.suffix.casefold() != ".pdf":
            raise ValueError(f"single paper analysis requires a PDF file: {self.pdf_path}")

    @property
    def papers_dir(self) -> Path:
        return self.out_dir / "papers"

    @property
    def results_dir(self) -> Path:
        return self.out_dir / "results"

    @property
    def reports_dir(self) -> Path:
        return self.out_dir / "reports"

    @property
    def major_domain(self) -> str:
        return "single_paper"

    @property
    def subdomain(self) -> str:
        return safe_path_name(self.title or self.pdf_path.stem)

    def run(self) -> dict[str, object]:
        self.start_monitor()
        try:
            layout = self.layout()
            paper_path = self.write_package(layout)
            agent = self.paper_agent_cls(
                input_dir=self.results_dir,
                results_dir=self.results_dir,
                reports_dir=self.reports_dir,
                provider=self.provider,
                model=self.model,
                cache_dir=self.cache_dir,
                base_url=self.base_url,
                overwrite=self.overwrite,
                workers=1,
                input_mode=self.input_mode,
                max_chunks_per_paper=self.max_chunks_per_paper,
                max_chunk_chars=self.max_chunk_chars,
                monitor=self.monitor,
            )
            agent_summary = agent.run()
            analysis_path = layout.analysis_domain_dir / "paper_001.analysis.json"
            report_paths = self.write_report(layout, paper_path, analysis_path, agent_summary)
            summary = {
                "pdf_path": str(self.pdf_path),
                "title": self.title or self.pdf_path.stem,
                "out_dir": str(self.out_dir),
                "package_dir": str(layout.data_domain_dir),
                "paper_path": str(paper_path),
                "analysis_path": str(analysis_path),
                "markdown": str(report_paths["markdown"]),
                "html": str(report_paths["html"]),
                "agent_summary": agent_summary,
                "monitor_status": str(self.monitor.status_path) if self.monitor else "",
            }
            summary_path = self.results_dir / "single_paper_summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["summary"] = str(summary_path)
            self.finish_monitor("completed", "Single paper analysis completed")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"Single paper analysis failed: {exc}")
            raise

    def layout(self) -> AnalysisLayout:
        return AnalysisLayout(
            papers_dir=self.papers_dir,
            results_dir=self.results_dir,
            reports_dir=self.reports_dir,
            major_domain=self.major_domain,
            subdomain=self.subdomain,
        )

    def write_package(self, layout: AnalysisLayout) -> Path:
        package_dir = layout.data_domain_dir
        papers_dir = package_dir / "papers"
        text_dir = package_dir / "extracted_text"
        papers_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)
        local_pdf_path = self.package_pdf(layout)
        text_path = self.extract_text(text_dir)
        article = ArticleRecord(
            title=self.title or self.pdf_path.stem,
            doi=self.doi,
            journal=self.journal,
            publish_date=self.publish_date,
            abstract=self.abstract,
            local_pdf_path=local_pdf_path,
            pdf_status="complete",
            download_status="local_pdf",
            subdomain="Single Paper",
            classification_source="local-pdf",
        )
        paper = self.paper_entry(article, text_path.relative_to(package_dir))
        paper_path = papers_dir / "paper_001.json"
        write_json(paper_path, paper)
        domain = {
            "domain_id": "domain_001",
            "domain_name": "Single Paper",
            "major_domain": layout.major_domain,
            "subdomain_dir": layout.subdomain,
            "taxonomy_source": "local-pdf",
            "paper_count": 1,
            "selected_paper_count": 1,
            "citation_count": 0,
            "papers": [paper],
        }
        write_json(package_dir / "domain.json", {key: value for key, value in domain.items() if key != "papers"})
        write_json(package_dir / "domain_manifest.json", domain)
        return paper_path

    def package_pdf(self, layout: AnalysisLayout) -> Path:
        if not self.copy_pdf:
            return self.pdf_path
        target_dir = layout.papers_domain_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_pdf_name(self.pdf_path.name)
        if self.overwrite or not target.exists():
            shutil.copy2(self.pdf_path, target)
        return target

    def extract_text(self, text_dir: Path) -> Path:
        text = self.extractor.extract_text(self.pdf_path)
        if self.max_text_chars and self.max_text_chars > 0:
            text = text[: self.max_text_chars]
        path = text_dir / "paper_001.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def paper_entry(self, article: ArticleRecord, text_path: Path) -> dict:
        return {
            "paper_id": "paper_001",
            "title": article.title,
            "doi": article.doi,
            "journal": article.journal,
            "year": extract_year(article.publish_date) or "",
            "publish_date": article.publish_date,
            "authors": [],
            "institutions": [],
            "abstract": article.abstract,
            "article_type": "",
            "domain": "Single Paper",
            "classification_source": article.classification_source,
            "classification_taxonomy": "",
            "classification_source_label": "Single Paper",
            "authoritative_topics": [],
            "citation_count": 0,
            "citation_source": "",
            "local_pdf_path": str(article.local_pdf_path),
            "pdf_status": article.pdf_status,
            "research_value_score": 0.0,
            "value_reason": "local PDF supplied by user",
            "journal_tier": "",
            "packaged_pdf_path": str(article.local_pdf_path),
            "text_path": str(text_path),
        }

    def write_report(self, layout: AnalysisLayout, paper_path: Path, analysis_path: Path, agent_summary: dict) -> dict[str, Path]:
        report_dir = layout.report_domain_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        paper = read_json(paper_path)
        analysis = read_json(analysis_path) if analysis_path.exists() else {}
        markdown = render_single_paper_report(paper, analysis, agent_summary)
        markdown_path = report_dir / "paper_report.md"
        html_path = report_dir / "paper_report.html"
        markdown_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(markdown_to_html(markdown, title=paper.get("title") or "Paper Report"), encoding="utf-8")
        return {"markdown": markdown_path, "html": html_path}

    def start_monitor(self) -> None:
        if self.monitor:
            self.monitor.start(
                "LitSurveyGrp analyze-pdf",
                "Analyzing one local PDF with the paper reader agent",
                metrics={"pdf_path": str(self.pdf_path), "provider": self.provider},
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def render_single_paper_report(paper: dict, analysis: dict, agent_summary: dict | None = None) -> str:
    title = paper.get("title") or "Single Paper Report"
    lines = [f"# {title}", ""]
    if paper.get("doi") or paper.get("journal") or paper.get("year"):
        lines.extend([
            "## Metadata",
            "",
            f"- DOI: {paper.get('doi') or 'not provided'}",
            f"- Journal: {paper.get('journal') or 'not provided'}",
            f"- Year: {paper.get('year') or 'not provided'}",
            f"- Source basis: {analysis.get('source_basis') or 'not available'}",
            "",
        ])
    sections = [
        ("Research Problem", analysis.get("research_problem", "")),
        ("Background Gap", analysis.get("background_gap", "")),
        ("Study Object", analysis.get("study_object", "")),
        ("Method Pipeline", analysis.get("method_pipeline", "")),
        ("Evidence Type", analysis.get("evidence_type", "")),
        ("Core Findings", analysis.get("core_findings", [])),
        ("Methods", analysis.get("methods", [])),
        ("Limitations", analysis.get("limitations", [])),
        ("Open Questions", analysis.get("open_questions", [])),
        ("Reusable Resources", analysis.get("reusable_resources", [])),
        ("Supporting Text", analysis.get("supporting_text", [])),
    ]
    for heading, value in sections:
        lines.extend([f"## {heading}", ""])
        lines.append(markdown_value(value))
        lines.append("")
    provider = (agent_summary or {}).get("provider")
    if provider:
        lines.extend(["## Run Metadata", "", f"- Agent provider: {provider}", f"- Model: {(agent_summary or {}).get('model') or 'not recorded'}", ""])
    return "\n".join(lines).strip() + "\n"


def markdown_value(value) -> str:
    if isinstance(value, list):
        if not value:
            return "- Not enough evidence in the supplied PDF."
        return "\n".join(f"- {item}" for item in value)
    value = str(value or "").strip()
    return value or "Not enough evidence in the supplied PDF."


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor = RunMonitor(Path(getattr(args, "monitor_dir", "") or Path(args.out) / "results"))
    service = SinglePaperAnalysisService(
        pdf_path=Path(args.pdf),
        out_dir=Path(args.out),
        title=getattr(args, "title", ""),
        doi=getattr(args, "doi", ""),
        journal=getattr(args, "journal", ""),
        publish_date=getattr(args, "publish_date", ""),
        abstract=getattr(args, "abstract", ""),
        provider=getattr(args, "model_provider", "dry-run"),
        model=getattr(args, "model", ""),
        base_url=getattr(args, "agent_base_url", ""),
        cache_dir=Path(args.agent_cache_dir) if getattr(args, "agent_cache_dir", None) else None,
        overwrite=getattr(args, "overwrite", False),
        input_mode=getattr(args, "agent_input_mode", "full-text"),
        max_chunks_per_paper=getattr(args, "agent_max_chunks_per_paper", 12),
        max_chunk_chars=getattr(args, "agent_max_chunk_chars", 2200),
        max_text_chars=getattr(args, "max_text_chars", 0),
        copy_pdf=getattr(args, "copy_pdf", False),
        monitor=monitor,
    )
    service.run()
    return 0
