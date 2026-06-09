# -*- coding: utf-8 -*-
"""Prepare domain-scoped inputs for LLM research agents."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from litsurveygrp.analysis_paths import AnalysisLayout, major_domain_name, subdomain_name
from litsurveygrp.paper_models import ArticleRecord
from litsurveygrp.reference_extractor import PdfReferenceExtractor
from litsurveygrp.research_stats import ResearchStatsWriter, extract_year
from litsurveygrp.run_monitor import RunMonitor


@dataclass
class AgentInputPreparer:
    """Build generic per-domain packages from a classified manifest."""

    manifest_path: Path
    out_dir: Path
    papers_dir: Path | None = None
    results_dir: Path | None = None
    reports_dir: Path | None = None
    top_domains: int = 10
    per_domain: int = 30
    copy_pdfs: bool = False
    extract_pdf_text: bool = False
    max_text_chars: int = 0
    project_name: str = ""
    selection: str = "domains"
    top_papers: int = 30
    monitor: RunMonitor | None = None

    def __post_init__(self) -> None:
        self.manifest_path = Path(self.manifest_path)
        self.out_dir = Path(self.out_dir)
        self.papers_dir = Path(self.papers_dir) if self.papers_dir else self.out_dir.parent / "papers"
        self.results_dir = Path(self.results_dir) if self.results_dir else self.out_dir.parent / "results"
        self.reports_dir = Path(self.reports_dir) if self.reports_dir else self.out_dir.parent / "reports"
        self.major_domain = major_domain_name(self.project_name)
        if self.selection not in {"domains", "top-downloaded-pdfs"}:
            raise ValueError(f"unsupported selection mode: {self.selection}")
        self.stats = ResearchStatsWriter(self.manifest_path, top_n=max(self.top_domains, 1))
        self.extractor = PdfReferenceExtractor()

    def run(self) -> dict:
        self.start_monitor()
        try:
            articles = self.stats.load_manifest()
            self.out_dir.mkdir(parents=True, exist_ok=True)
            if self.selection == "top-downloaded-pdfs":
                packages = self.run_top_downloaded_pdf_selection(articles)
                summary = self.build_summary(packages)
                self.write_json(self.out_dir / "agent_input_summary.json", summary)
                self.update_monitor(
                    "prepare_agent_input",
                    "Prepared top downloaded PDF agent input package",
                    processed=len(packages),
                    total=len(packages),
                    metrics={"packages": len(packages), "selected_papers": sum(item["selected_paper_count"] for item in packages)},
                )
                self.finish_monitor("completed", f"Prepared {len(packages)} agent input packages")
                return summary

            domains = self.select_domains(articles)
            self.update_monitor(
                "prepare_agent_input",
                "Selected top domains for agent input",
                processed=0,
                total=len(domains),
                metrics={"source_papers": len(articles)},
            )
            packages = []
            for index, domain in enumerate(domains, start=1):
                selected = self.select_domain_papers(domain, articles)
                self.update_monitor(
                    "prepare_agent_input",
                    "Writing domain agent package",
                    processed=index - 1,
                    total=len(domains),
                    current_item=domain["subdomain"],
                    metrics={"selected_papers": len(selected)},
                )
                packages.append(self.write_domain_package(index, domain, selected))
            summary = self.build_summary(packages)
            self.write_json(self.out_dir / "agent_input_summary.json", summary)
            self.update_monitor(
                "prepare_agent_input",
                "Finished writing agent input packages",
                processed=len(packages),
                total=len(domains),
                metrics={"packages": len(packages)},
            )
            self.finish_monitor("completed", f"Prepared {len(packages)} agent input packages")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"Agent input preparation failed: {exc}")
            raise

    def build_summary(self, packages: list[dict]) -> dict:
        return {
            "project_name": self.project_name,
            "source_manifest": str(self.manifest_path),
            "results_dir": str(self.results_dir),
            "reports_dir": str(self.reports_dir),
            "agent_package_dir": str(self.out_dir),
            "papers_dir": str(self.papers_dir),
            "major_domain": self.major_domain,
            "selection": self.selection,
            "top_domains": self.top_domains,
            "per_domain": self.per_domain,
            "top_papers": self.top_papers,
            "domain_count": len(packages),
            "packages": packages,
            "monitor_status": str(self.monitor.status_path) if self.monitor else "",
        }

    def run_top_downloaded_pdf_selection(self, articles: list[ArticleRecord]) -> list[dict]:
        selected = self.select_top_downloaded_pdf_papers(articles)
        groups: dict[str, list[tuple[ArticleRecord, dict]]] = defaultdict(list)
        for article, ranking in selected:
            groups[article.subdomain or "Other"].append((article, ranking))
        self.update_monitor(
            "prepare_agent_input",
            "Selected top downloaded PDFs for agent input",
            processed=0,
            total=len(groups),
            metrics={"source_papers": len(articles), "selected_papers": len(selected)},
        )
        packages = []
        for index, (subdomain, papers) in enumerate(sorted(groups.items()), start=1):
            domain = {
                "subdomain": subdomain,
                "paper_count": len(papers),
                "citation_count": sum(int(article.citation_count or 0) for article, _ in papers),
            }
            packages.append(self.write_domain_package(index, domain, papers))
        return packages

    def select_top_downloaded_pdf_papers(self, articles: list[ArticleRecord]) -> list[tuple[ArticleRecord, dict]]:
        downloaded = [
            article for article in articles
            if article.local_pdf_path and article.pdf_status == "complete" and Path(article.local_pdf_path).exists()
        ]
        max_citations = max([int(article.citation_count or 0) for article in downloaded] or [0])
        ranked = []
        for article in downloaded:
            score, reason, tier = self.stats.paper_value(article, max_citations)
            ranked.append((article, {
                "research_value_score": score,
                "value_reason": reason,
                "journal_tier": tier,
            }))
        ranked.sort(key=lambda item: (-item[1]["research_value_score"], -int(item[0].citation_count or 0), item[0].title.lower()))
        if self.per_domain > 0:
            grouped: dict[str, list[tuple[ArticleRecord, dict]]] = defaultdict(list)
            for item in ranked:
                grouped[item[0].subdomain or "Other"].append(item)
            selected: list[tuple[ArticleRecord, dict]] = []
            for _, items in sorted(
                grouped.items(),
                key=lambda group: (
                    -len(group[1]),
                    -sum(int(item[0].citation_count or 0) for item in group[1]),
                    group[0],
                ),
            ):
                selected.extend(items[: self.per_domain])
            return selected[: self.top_papers] if self.top_papers > 0 else selected
        return ranked[: self.top_papers]

    def select_domains(self, articles: list[ArticleRecord]) -> list[dict]:
        rows = [
            row for row in self.stats.subdomain_stats(articles)
            if not str(row.get("subdomain", "")).startswith("其他领域")
        ]
        rows.sort(key=lambda row: (-int(row.get("paper_count") or 0), -int(row.get("citation_count") or 0), row["subdomain"]))
        return rows[: self.top_domains]

    def select_domain_papers(self, domain: dict, articles: list[ArticleRecord]) -> list[tuple[ArticleRecord, dict]]:
        name = domain["subdomain"]
        group = [article for article in articles if (article.subdomain or "Other") == name]
        max_citations = max([int(article.citation_count or 0) for article in group] or [0])
        ranked = []
        for article in group:
            score, reason, tier = self.stats.paper_value(article, max_citations)
            ranked.append((article, {
                "research_value_score": score,
                "value_reason": reason,
                "journal_tier": tier,
            }))
        ranked.sort(key=lambda item: (-item[1]["research_value_score"], -int(item[0].citation_count or 0), item[0].title.lower()))
        return ranked[: self.per_domain]

    def write_domain_package(self, index: int, domain: dict, selected: list[tuple[ArticleRecord, dict]]) -> dict:
        package_id = f"domain_{index:03d}"
        layout = self.layout_for_domain(domain)
        package_dir = layout.data_domain_dir
        papers_dir = package_dir / "papers"
        text_dir = package_dir / "extracted_text"
        papers_dir.mkdir(parents=True, exist_ok=True)
        if self.extract_pdf_text:
            text_dir.mkdir(parents=True, exist_ok=True)

        paper_entries = []
        for paper_index, (article, ranking) in enumerate(selected, start=1):
            paper_id = f"paper_{paper_index:03d}"
            entry = self.paper_entry(paper_id, article, ranking)
            entry["packaged_pdf_path"] = str(article.local_pdf_path) if article.local_pdf_path else ""
            if self.extract_pdf_text:
                entry["text_path"] = self.extract_text(article, package_dir, text_dir, paper_id)
            self.write_json(papers_dir / f"{paper_id}.json", entry)
            paper_entries.append(entry)

        domain_manifest = {
            "domain_id": package_id,
            "domain_name": domain["subdomain"],
            "major_domain": layout.major_domain,
            "subdomain_dir": layout.subdomain,
            "taxonomy_source": self.domain_taxonomy_source(paper_entries),
            "paper_count": int(domain.get("paper_count") or 0),
            "selected_paper_count": len(paper_entries),
            "citation_count": int(domain.get("citation_count") or 0),
            "papers": paper_entries,
        }
        self.write_json(package_dir / "domain.json", {
            key: value for key, value in domain_manifest.items() if key != "papers"
        })
        self.write_json(package_dir / "domain_manifest.json", domain_manifest)
        return {
            "domain_id": package_id,
            "domain_name": domain["subdomain"],
            "path": str(package_dir),
            "data_path": str(layout.data_domain_dir),
            "papers_path": str(layout.papers_domain_dir),
            "analysis_path": str(layout.analysis_domain_dir),
            "report_path": str(layout.report_domain_dir),
            "selected_paper_count": len(paper_entries),
        }

    def layout_for_domain(self, domain: dict) -> AnalysisLayout:
        return AnalysisLayout(
            papers_dir=self.papers_dir,
            results_dir=self.results_dir,
            reports_dir=self.reports_dir,
            major_domain=self.major_domain,
            subdomain=subdomain_name(domain.get("subdomain", ""), "general"),
        )

    def paper_entry(self, paper_id: str, article: ArticleRecord, ranking: dict) -> dict:
        return {
            "paper_id": paper_id,
            "title": article.title,
            "doi": article.doi,
            "journal": article.journal,
            "year": extract_year(article.publish_date) or "",
            "publish_date": article.publish_date,
            "authors": list(article.authors),
            "institutions": list(article.institutions),
            "abstract": article.abstract,
            "article_type": article.article_type,
            "domain": article.subdomain or "Other",
            "classification_source": article.classification_source,
            "classification_taxonomy": article.classification_taxonomy,
            "classification_source_label": article.classification_source_label,
            "authoritative_topics": list(article.authoritative_topics),
            "citation_count": int(article.citation_count or 0),
            "citation_source": article.citation_source,
            "local_pdf_path": str(article.local_pdf_path) if article.local_pdf_path else "",
            "pdf_status": article.pdf_status,
            "research_value_score": ranking["research_value_score"],
            "value_reason": ranking["value_reason"],
            "journal_tier": ranking["journal_tier"],
        }

    def extract_text(self, article: ArticleRecord, package_dir: Path, text_dir: Path, paper_id: str) -> str:
        if not article.local_pdf_path:
            return ""
        source = Path(article.local_pdf_path)
        if not source.exists():
            return ""
        try:
            text = self.extractor.extract_text(source)
            if self.max_text_chars and self.max_text_chars > 0:
                text = text[: self.max_text_chars]
        except Exception:
            return ""
        path = text_dir / f"{paper_id}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path.relative_to(package_dir))

    def domain_taxonomy_source(self, papers: list[dict]) -> str:
        counts = defaultdict(int)
        for paper in papers:
            counts[paper.get("classification_source") or "unknown"] += 1
        if not counts:
            return "unknown"
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def start_monitor(self) -> None:
        if self.monitor:
            self.monitor.start(
                "LitSurveyGrp agent input preparation",
                "Preparing per-domain packages for research agents",
                metrics={
                    "manifest": str(self.manifest_path),
                    "out_dir": str(self.out_dir),
                    "papers_dir": str(self.papers_dir),
                    "results_dir": str(self.results_dir),
                    "reports_dir": str(self.reports_dir),
                    "major_domain": self.major_domain,
                    "top_domains": self.top_domains,
                    "per_domain": self.per_domain,
                    "selection": self.selection,
                    "top_papers": self.top_papers,
                    "copy_pdfs": self.copy_pdfs,
                    "extract_pdf_text": self.extract_pdf_text,
                },
            )

    def update_monitor(
        self,
        stage: str,
        message: str,
        processed: int | None = None,
        total: int | None = None,
        current_item: str | None = None,
        metrics: dict | None = None,
    ) -> None:
        if self.monitor:
            self.monitor.update(
                stage=stage,
                message=message,
                processed=processed,
                total=total,
                current_item=current_item,
                metrics=metrics,
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def safe_name(value: str, max_length: int = 120) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    value = re.sub(r"\s+", "_", value).strip("._")
    return (value or "item")[:max_length]


def safe_pdf_name(value: str, max_length: int = 120) -> str:
    path = Path(str(value or "paper.pdf"))
    suffix = path.suffix if path.suffix else ".pdf"
    if suffix.casefold() != ".pdf":
        suffix = ".pdf"
    stem_limit = max(1, max_length - len(suffix))
    stem = safe_name(path.stem or "paper", max_length=stem_limit)
    return stem + suffix


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor_dir = Path(getattr(args, "monitor_dir", "") or args.out_dir)
        monitor = RunMonitor(monitor_dir)
    preparer = AgentInputPreparer(
        manifest_path=Path(args.manifest),
        out_dir=Path(args.out_dir),
        papers_dir=Path(args.papers_dir) if getattr(args, "papers_dir", None) else None,
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        reports_dir=Path(args.reports_dir) if getattr(args, "reports_dir", None) else None,
        top_domains=getattr(args, "top_domains", 10),
        per_domain=getattr(args, "per_domain", 30),
        copy_pdfs=getattr(args, "copy_pdfs", False),
        extract_pdf_text=getattr(args, "extract_pdf_text", False),
        max_text_chars=getattr(args, "max_text_chars", 0),
        project_name=getattr(args, "project_name", ""),
        selection=getattr(args, "selection", "domains"),
        top_papers=getattr(args, "top_papers", 30),
        monitor=monitor,
    )
    preparer.run()
    return 0
