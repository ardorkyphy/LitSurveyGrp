# -*- coding: utf-8 -*-
"""Build a readable multi-domain academic survey report from pipeline outputs."""

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agents.domain_synthesizer_agent import domain_evidence_coverage
from litsurveygrp.analysis_paths import AnalysisLayout, major_domain_name, report_data_dir, subdomain_name


@dataclass
class FinalSurveyReportBuilder:
    """Generate Markdown and HTML reports from existing survey artifacts."""

    results_dir: Path
    agent_dir: Path | None = None
    reports_dir: Path | None = None
    out: Path | None = None
    html_out: Path | None = None
    title: str = ""
    max_domains: int = 10
    max_papers_per_domain: int = 8
    max_recommended_papers: int = 12

    def __post_init__(self) -> None:
        self.results_dir = Path(self.results_dir)
        self.agent_dir = Path(self.agent_dir) if self.agent_dir else None
        self.reports_dir = Path(self.reports_dir) if self.reports_dir else self.results_dir.parent / "reports"
        self.out = Path(self.out) if self.out else None
        self.html_out = Path(self.html_out) if self.html_out else None

    def build(self) -> dict[str, Path]:
        data = self.load_context()
        self.ensure_output_paths(data)
        markdown = self.render_markdown(data)
        self.write_text(self.out, markdown)
        self.write_text(self.html_out, markdown_to_html(markdown, title=data["title"]))
        return {"markdown": self.out, "html": self.html_out}

    def load_context(self) -> dict:
        overview_dir = self.report_overview_dir()
        pipeline = self.read_json(overview_dir / "pipeline_report.json", {}) or self.read_json(self.results_dir / "pipeline_report.json", {})
        summary = self.read_json(overview_dir / "stats" / "summary.json", {}) or self.read_json(self.results_dir / "stats" / "summary.json", {})
        profile = self.read_json(overview_dir / "stats" / "research_profile.json", {}) or self.read_json(self.results_dir / "stats" / "research_profile.json", {})
        pdf_summary = self.read_json(overview_dir / "pdf_download_summary.json", {}) or self.read_json(self.results_dir / "pdf_download_summary.json", {})
        agent_summary = self.read_json(self.agent_dir / "agent_input_summary.json", {}) if self.agent_dir else {}
        paper_reader_summary = self.first_analysis_summary("paper_reader_summary.json")
        domain_synth_summary = self.first_analysis_summary("domain_synthesizer_summary.json")
        if self.agent_dir:
            paper_reader_summary = paper_reader_summary or self.read_json(self.agent_dir / "paper_reader_summary.json", {})
            domain_synth_summary = domain_synth_summary or self.read_json(self.agent_dir / "domain_synthesizer_summary.json", {})
        domains = self.load_domain_reports()
        manifest = self.read_json(Path(pipeline.get("final_manifest", "")), [])
        if not manifest:
            manifest = self.read_json(overview_dir / "classified_manifest.json", {}) or self.read_json(self.results_dir / "classified_manifest.json", [])
        title = self.title or inferred_title(pipeline, agent_summary)
        return {
            "title": title,
            "pipeline": pipeline,
            "summary": summary,
            "profile": profile,
            "pdf_summary": pdf_summary,
            "agent_summary": agent_summary,
            "paper_reader_summary": paper_reader_summary,
            "domain_synth_summary": domain_synth_summary,
            "domains": domains[: self.max_domains],
            "manifest": manifest if isinstance(manifest, list) else [],
        }

    def ensure_output_paths(self, data: dict) -> None:
        report_dir = self.default_report_dir(data)
        if self.out is None:
            self.out = report_dir / "final_survey_report.md"
        if self.html_out is None:
            self.html_out = report_dir / "final_survey_report.html"

    def default_report_dir(self, data: dict) -> Path:
        agent_summary = data.get("agent_summary") or {}
        domains = data.get("domains") or []
        packages = agent_summary.get("packages") or []

        if len(packages) == 1:
            package = packages[0]
            report_path = package.get("report_path")
            if report_path:
                return Path(report_path)

        if len(domains) == 1:
            manifest = domains[0].get("manifest") or {}
            return self.layout_for_domain(domains[0]["domain_dir"], manifest).report_domain_dir

        major_domain = agent_summary.get("major_domain") or major_domain_name(
            agent_summary.get("project_name") or data.get("title") or "survey"
        )
        return report_data_dir(self.reports_dir, major_domain)

    def load_domain_reports(self) -> list[dict]:
        if not self.agent_dir or not self.agent_dir.exists():
            return []
        domains = []
        for domain_dir in self.domain_input_dirs():
            if not domain_dir.is_dir():
                continue
            manifest = self.read_json(domain_dir / "domain_manifest.json", {})
            layout = self.layout_for_domain(domain_dir, manifest)
            analysis_dir = layout.analysis_domain_dir
            synthesis = self.read_json(analysis_dir / "domain_synthesis.json", {})
            if not synthesis:
                synthesis = self.read_json(self.legacy_analysis_dir_for_domain(domain_dir, manifest) / "domain_synthesis.json", {})
            if not synthesis:
                synthesis = self.read_json(domain_dir / "domain_synthesis.json", {})
            if synthesis and synthesis.get("validation_status", "valid") != "valid":
                synthesis = {}
            analyses = []
            paper_analysis_dir = self.first_existing_dir(
                analysis_dir,
                self.legacy_analysis_dir_for_domain(domain_dir, manifest),
                domain_dir / "paper_analysis",
            )
            for path in sorted(paper_analysis_dir.glob("*.analysis.json")):
                paper_path = domain_dir / "papers" / path.name.replace(".analysis.json", ".json")
                paper = self.read_json(paper_path, {})
                analysis = self.read_json(path, {})
                if analysis.get("validation_status", "valid") != "valid":
                    continue
                analyses.append({"paper": paper, "analysis": analysis})
            domains.append({
                "domain_dir": domain_dir,
                "manifest": manifest,
                "synthesis": synthesis,
                "analyses": analyses,
                "coverage": synthesis.get("domain_evidence_coverage") or domain_evidence_coverage(manifest, analyses),
            })
        return domains

    def domain_input_dirs(self) -> list[Path]:
        legacy = [
            path
            for path in sorted(self.agent_dir.glob("domain_*"))
            if path.is_dir() and (path / "domain_manifest.json").exists()
        ]
        nested = [
            path.parent
            for path in sorted(self.agent_dir.rglob("domain_manifest.json"))
            if (path.parent / "papers").exists()
        ]
        seen = set()
        domains = []
        for path in [*legacy, *nested]:
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                domains.append(path)
        return domains

    def first_analysis_summary(self, filename: str) -> dict:
        roots = [self.results_dir, self.results_dir / "analysis"]
        seen = set()
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob(filename)):
                key = path.resolve()
                if key in seen:
                    continue
                seen.add(key)
                data = self.read_json(path, {})
                if data:
                    return data
        return {}

    def layout_for_domain(self, domain_dir: Path, manifest: dict) -> AnalysisLayout:
        return AnalysisLayout(
            papers_dir=self.results_dir.parent / "papers",
            results_dir=self.results_dir,
            reports_dir=self.reports_dir,
            major_domain=manifest.get("major_domain") or major_domain_name(manifest.get("domain_name", "")),
            subdomain=manifest.get("subdomain_dir") or subdomain_name(manifest.get("domain_name", ""), domain_dir.name),
        )

    def legacy_analysis_dir_for_domain(self, domain_dir: Path, manifest: dict) -> Path:
        major_domain = manifest.get("major_domain") or major_domain_name(manifest.get("domain_name", ""))
        subdomain = manifest.get("subdomain_dir") or subdomain_name(manifest.get("domain_name", ""), domain_dir.name)
        return self.results_dir / major_domain / subdomain

    def first_existing_dir(self, *paths: Path) -> Path:
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    def render_markdown(self, data: dict) -> str:
        lines = []
        add = lines.append
        title = data["title"]
        summary = data["summary"]
        pipeline = data["pipeline"]
        pdf_summary = data["pdf_summary"]
        profile = data["profile"]
        domains = data["domains"]

        add(f"# {title}")
        add("")
        add("## Abstract")
        add("")
        add(self.abstract_paragraph(data))
        add("")

        add("## 1. Introduction")
        add("")
        add(
            "This report summarizes a multi-domain literature survey generated from open scholarly "
            "metadata and structured downstream analysis. The survey treats the query as an entry "
            "point into a heterogeneous research landscape rather than as a manually delimited field; "
            "therefore, the resulting domains include both core neuroscience topics and adjacent "
            "computational, clinical, educational, and methodological areas."
        )
        add("")

        add("## 2. Data Sources and Methodology")
        add("")
        add(f"- Query or source: {pipeline.get('query') or ', '.join(pipeline.get('journals') or []) or 'not recorded'}")
        add(f"- Records analyzed: {summary.get('total_papers', len(data['manifest']))}")
        add(f"- Year range: {summary.get('year_min', 'unknown')} to {summary.get('year_max', 'unknown')}")
        add(f"- Metadata sources: {', '.join(pipeline.get('metadata_sources') or []) or 'not recorded'}")
        add(f"- Classification source: {classification_source_summary(summary)}")
        add(f"- Collection mode: {pipeline.get('collection_mode', 'not recorded')}")
        if pdf_summary:
            add(
                "- PDF acquisition: "
                f"{pdf_summary.get('completed_pdfs', 0)} completed from "
                f"{pdf_summary.get('selected_for_download', 0)} selected Top papers"
            )
        add(f"- Agent analysis provider: {data['paper_reader_summary'].get('provider') or 'not available'}")
        if data["paper_reader_summary"].get("input_mode"):
            add(f"- Agent evidence mode: {data['paper_reader_summary'].get('input_mode')}")
        add(f"- Domain synthesis provider: {data['domain_synth_summary'].get('provider') or 'not available'}")
        if uses_dry_run(data):
            add("- Important note: the agent outputs were produced with `dry-run`; they are structural placeholders, not semantic LLM-authored analysis.")
        add("")

        add("## 3. Overall Landscape")
        add("")
        add(self.landscape_paragraph(summary, profile, pdf_summary))
        add("")
        add("### 3.1 Leading Domains")
        add("")
        add(markdown_table(
            ["Domain", "Papers", "Citations"],
            [
                [row.get("subdomain", ""), row.get("paper_count", 0), row.get("citation_count", 0)]
                for row in (summary.get("top_subdomains") or [])[:10]
            ],
        ))
        add("")
        add("### 3.2 Influential Journals and Institutions")
        add("")
        add("Leading journals by citation volume include:")
        add("")
        add(bullets(format_count_rows(summary.get("top_journals_by_citations") or [], "journal", limit=8)))
        add("")
        add("Leading institutions by citation volume include:")
        add("")
        add(bullets(format_count_rows(summary.get("top_institutions_by_citations") or [], "institution", limit=8)))
        add("")

        add("### 3.3 Domain Evidence Coverage")
        add("")
        add(markdown_table(
            ["Domain", "Selected", "PDF Text", "Abstract Only", "Metadata Only", "Evidence Chunks", "Reliability"],
            [
                [
                    (domain.get("manifest") or {}).get("domain_name") or (domain.get("synthesis") or {}).get("domain", ""),
                    (domain.get("coverage") or {}).get("selected_papers", 0),
                    (domain.get("coverage") or {}).get("papers_analyzed_from_pdf_text", 0),
                    (domain.get("coverage") or {}).get("papers_analyzed_from_abstract_only", 0),
                    (domain.get("coverage") or {}).get("papers_analyzed_from_metadata_only", 0),
                    (domain.get("coverage") or {}).get("papers_with_selected_evidence_chunks", 0),
                    (domain.get("coverage") or {}).get("reliability", "low"),
                ]
                for domain in domains
            ],
        ))
        add("")

        add("## 4. Domain-Level Findings")
        add("")
        if not domains:
            add("No agent domain packages were available. This section is limited to aggregate statistical profiles.")
            add("")
        for index, domain in enumerate(domains, start=1):
            self.render_domain_section(lines, index, domain)

        add("## 5. Cross-Domain Methodological Patterns")
        add("")
        add(self.cross_domain_patterns(domains, profile))
        add("")

        add("## 6. Research Gaps and Future Directions")
        add("")
        add(self.gaps_and_future_directions(domains))
        add("")

        add("## 7. Recommended Reading Path")
        add("")
        add(self.recommended_reading(profile, domains))
        add("")

        add("## 8. Limitations")
        add("")
        add("- OpenAlex metadata and topic assignments are authoritative external metadata, but they can still be incomplete or mismatched for interdisciplinary queries.")
        add("- Citation counts are source-dependent and should not be interpreted as formal bibliometric ground truth.")
        add("- PDF-based evidence is limited to openly accessible full text; papers without downloaded PDFs may rely on metadata or abstracts only.")
        if uses_dry_run(data):
            add("- Because the current agent provider is `dry-run`, paper and domain syntheses should be treated as report scaffolding rather than substantive LLM interpretation.")
        add("- The report is generated from retrieved records and does not claim exhaustive coverage of the field.")
        add("")

        add("## Source Paper Index")
        add("")
        add(self.source_paper_index(profile, domains))
        add("")

        add("## Output Files")
        add("")
        add(f"- Dashboard: `{relative_or_str(self.report_overview_dir() / 'visualization' / 'research_dashboard.html')}`")
        add(f"- Classified manifest: `{relative_or_str(self.report_overview_dir() / 'classified_manifest.json')}`")
        if self.agent_dir:
            add(f"- Agent metadata directory: `{relative_or_str(self.agent_dir)}`")
        add(f"- Agent result directory: `{relative_or_str(self.results_dir)}`")
        add(f"- Domain report directory: `{relative_or_str(self.reports_dir)}`")
        add(f"- Markdown report: `{relative_or_str(self.out)}`")
        add(f"- HTML report: `{relative_or_str(self.html_out)}`")
        add("")
        return "\n".join(lines)

    def render_domain_section(self, lines: list[str], index: int, domain: dict) -> None:
        manifest = domain["manifest"]
        synthesis = domain["synthesis"]
        analyses = domain["analyses"]
        name = manifest.get("domain_name") or synthesis.get("domain") or f"Domain {index}"
        lines.append(f"### 4.{index}. {name}")
        lines.append("")
        lines.append(
            f"This domain contains {manifest.get('paper_count', 'unknown')} retrieved papers; "
            f"{manifest.get('selected_paper_count', len(analyses))} papers were selected for agent packaging. "
            f"The taxonomy source is `{manifest.get('taxonomy_source', 'unknown')}`."
        )
        lines.append("")
        coverage = domain.get("coverage") or {}
        if coverage:
            lines.append(
                "Evidence coverage: "
                f"{coverage.get('papers_analyzed_from_pdf_text', 0)} full-text PDF analyses, "
                f"{coverage.get('papers_analyzed_from_abstract_only', 0)} abstract-only analyses, "
                f"{coverage.get('papers_analyzed_from_metadata_only', 0)} metadata-only analyses; "
                f"reliability is `{coverage.get('reliability', 'low')}`."
            )
            note = coverage.get("reliability_note")
            if note:
                lines.append("")
                lines.append(f"Reliability note: {note}")
            lines.append("")
        if synthesis and not is_empty_synthesis(synthesis):
            lines.append(f"**Synthesis.** {synthesis.get('one_sentence_summary', '').strip()}")
            lines.append("")
            self.add_list_section(lines, "Core problems", synthesis.get("core_problem_system") or [])
            self.add_list_section(lines, "Methods", synthesis.get("method_system") or [])
            self.add_list_section(lines, "Research gaps", synthesis.get("research_gaps") or [])
        else:
            lines.append(
                "**Synthesis status.** No substantive semantic synthesis is available for this domain. "
                "The report therefore uses metadata, paper ranking, and available abstracts as the domain summary."
            )
            lines.append("")
        lines.append("Representative papers:")
        lines.append("")
        rows = []
        for item in analyses[: self.max_papers_per_domain]:
            paper = item["paper"]
            analysis = item["analysis"]
            basis = analysis.get("source_basis", "unknown")
            rows.append([
                paper.get("title", ""),
                paper.get("year", ""),
                paper.get("journal", ""),
                paper.get("citation_count", 0),
                basis,
            ])
        lines.append(markdown_table(["Title", "Year", "Journal", "Citations", "Basis"], rows))
        lines.append("")
        evidence_rows = self.evidence_trace_rows(synthesis, analyses)
        if evidence_rows:
            lines.append("Evidence trace:")
            lines.append("")
            lines.append(markdown_table(
                ["Claim", "Paper", "Evidence", "Section", "Supporting text"],
                evidence_rows,
            ))
            lines.append("")

    def add_list_section(self, lines: list[str], title: str, values: list) -> None:
        if not values:
            return
        lines.append(f"**{title}.**")
        lines.append("")
        lines.append(bullets([str(value) for value in values[:8]]))
        lines.append("")

    def evidence_trace_rows(self, synthesis: dict, analyses: list[dict]) -> list[list[str]]:
        if not analyses:
            return []
        by_reference = {}
        for item in analyses:
            paper = item.get("paper") or {}
            paper_id = paper.get("paper_id") or ""
            title = paper.get("title") or ""
            for key in [paper_id, title, normalize_title_ref(title)]:
                if key:
                    by_reference[str(key)] = item

        rows = []
        for evidence in synthesis.get("evidence_index") or []:
            if not isinstance(evidence, dict):
                continue
            claim = str(evidence.get("claim") or "").strip()
            for paper_ref in evidence.get("papers") or []:
                item = by_reference.get(str(paper_ref)) or by_reference.get(normalize_title_ref(str(paper_ref)))
                if not item:
                    rows.append([short_cell(claim), short_cell(str(paper_ref)), "", "", ""])
                    continue
                rows.append(self.evidence_row(claim, item))
                if len(rows) >= 12:
                    return rows

        if rows:
            return rows
        for item in analyses[: self.max_papers_per_domain]:
            analysis = item.get("analysis") or {}
            claim = analysis.get("research_problem") or first_string(analysis.get("core_findings")) or ""
            if not claim:
                continue
            rows.append(self.evidence_row(str(claim), item))
            if len(rows) >= 8:
                break
        return rows

    def evidence_row(self, claim: str, item: dict) -> list[str]:
        paper = item.get("paper") or {}
        analysis = item.get("analysis") or {}
        evidence_chunk = first_dict(analysis.get("evidence_chunks"))
        supporting_text = first_string(analysis.get("supporting_text"))
        evidence_id = evidence_chunk.get("chunk_id", "") if evidence_chunk else ""
        section = evidence_chunk.get("section", "") if evidence_chunk else ""
        paper_label = paper.get("paper_id") or paper.get("title") or "paper"
        if paper.get("title") and paper.get("paper_id"):
            paper_label = f"{paper.get('paper_id')}: {paper.get('title')}"
        return [
            short_cell(claim),
            short_cell(paper_label),
            short_cell(evidence_id),
            short_cell(section),
            short_cell(supporting_text),
        ]

    def abstract_paragraph(self, data: dict) -> str:
        summary = data["summary"]
        pipeline = data["pipeline"]
        pdf_summary = data["pdf_summary"]
        domains = data["domains"]
        return (
            f"This survey analyzes {summary.get('total_papers', len(data['manifest']))} records retrieved for "
            f"`{pipeline.get('query') or 'the configured literature source'}`. The corpus spans "
            f"{summary.get('year_min', 'unknown')} to {summary.get('year_max', 'unknown')} and includes "
            f"{summary.get('total_citations', 0)} total open-source citation counts. "
            f"The analysis identifies {len(domains)} packaged domains for downstream research synthesis. "
            f"PDF acquisition completed for {pdf_summary.get('completed_pdfs', 0) if pdf_summary else 0} selected papers. "
            "The report summarizes the overall research landscape, domain-level themes, recommended reading paths, "
            "and methodological limitations."
        )

    def landscape_paragraph(self, summary: dict, profile: dict, pdf_summary: dict) -> str:
        topic_count = len((summary.get("top_subdomains") or []))
        return (
            f"The retrieved corpus contains {summary.get('total_papers', 0)} papers, "
            f"{summary.get('unique_authors', 0)} unique authors, and "
            f"{summary.get('unique_institutions', 0)} unique institutions. "
            f"The mean citation count is {summary.get('average_citations', 0)}, with a median of "
            f"{summary.get('median_citations', 0)}. The dashboard-level topic profile reports "
            f"{topic_count} displayed domain groups, including an aggregated long tail when applicable. "
            f"Among selected PDF candidates, {pdf_summary.get('completed_pdfs', 0) if pdf_summary else 0} were acquired."
        )

    def cross_domain_patterns(self, domains: list[dict], profile: dict) -> str:
        labels = [domain["manifest"].get("domain_name", "") for domain in domains]
        tokens = keyword_summary(" ".join(labels), limit=8)
        if tokens:
            return (
                "Across the packaged domains, recurring methodological signals include "
                + ", ".join(tokens)
                + ". These signals suggest that the field is organized around both computational modeling "
                "and empirical neuroscience workflows, with adjacent clinical, educational, and hardware-oriented themes."
            )
        growing = [row.get("subdomain", "") for row in profile.get("growing_topics", [])[:5]]
        if growing:
            return "The most visible cross-domain pattern is the rise of " + "; ".join(growing) + "."
        return "The available artifacts do not provide enough evidence to infer strong cross-domain methodological patterns."

    def gaps_and_future_directions(self, domains: list[dict]) -> str:
        gaps = []
        for domain in domains:
            gaps.extend(domain["synthesis"].get("research_gaps") or [])
        if gaps:
            return bullets([str(gap) for gap in gaps[:12]])
        return bullets([
            "Improve reproducibility by linking AI-neuroscience claims to open datasets, evaluation protocols, and full methodological descriptions.",
            "Differentiate papers that use AI as an analytic instrument from papers that study AI as a cognitive or neuroscientific model.",
            "Assess robustness across cohorts, imaging or signal modalities, and institutions before translating AI systems into clinical or educational settings.",
            "Clarify ethical, interpretability, and governance constraints when AI is used for neural decoding, diagnosis, intervention, or human enhancement.",
        ])

    def recommended_reading(self, profile: dict, domains: list[dict]) -> str:
        recommendations = []
        for key in ["review_entry_points", "classic_papers", "recent_high_potential_papers"]:
            for row in profile.get(key, [])[: self.max_recommended_papers]:
                title = row.get("title", "")
                if title and title not in {item[0] for item in recommendations}:
                    recommendations.append((title, row.get("year", ""), row.get("journal", ""), row.get("doi", "")))
                if len(recommendations) >= self.max_recommended_papers:
                    break
            if len(recommendations) >= self.max_recommended_papers:
                break
        if not recommendations:
            for domain in domains:
                for item in domain["analyses"]:
                    paper = item["paper"]
                    if paper.get("title"):
                        recommendations.append((paper.get("title", ""), paper.get("year", ""), paper.get("journal", ""), paper.get("doi", "")))
                    if len(recommendations) >= self.max_recommended_papers:
                        break
        rows = [[title, year, journal, doi] for title, year, journal, doi in recommendations]
        return markdown_table(["Title", "Year", "Journal", "DOI"], rows)

    def source_paper_index(self, profile: dict, domains: list[dict]) -> str:
        rows = []
        seen = set()
        for domain in domains:
            for item in domain["analyses"][:3]:
                paper = item["paper"]
                key = paper.get("doi") or paper.get("title")
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append([
                    paper.get("title", ""),
                    paper.get("year", ""),
                    paper.get("domain", ""),
                    paper.get("doi", ""),
                ])
        return markdown_table(["Title", "Year", "Domain", "DOI"], rows[:30])

    def read_json(self, path: Path, default):
        try:
            path = Path(path)
            if not path.exists():
                return default
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def report_overview_dir(self) -> Path:
        agent_summary = self.read_json(self.agent_dir / "agent_input_summary.json", {}) if self.agent_dir else {}
        major_domain = agent_summary.get("major_domain") or major_domain_name(agent_summary.get("project_name") or "survey")
        return report_data_dir(self.reports_dir, major_domain)


def inferred_title(pipeline: dict, agent_summary: dict) -> str:
    query = pipeline.get("query") or agent_summary.get("project_name") or "Literature Survey"
    return f"{query}: A Multi-Domain Literature Survey"


def classification_source_summary(summary: dict) -> str:
    rows = summary.get("classification_sources") or []
    if not rows:
        return "not recorded"
    return ", ".join(f"{row.get('classification_source', 'unknown')} ({row.get('paper_count', 0)})" for row in rows)


def uses_dry_run(data: dict) -> bool:
    return any(
        (data.get(key) or {}).get("provider") == "dry-run"
        for key in ["paper_reader_summary", "domain_synth_summary"]
    )


def is_empty_synthesis(synthesis: dict) -> bool:
    if not synthesis:
        return True
    list_keys = [
        "core_problem_system",
        "method_system",
        "problem_method_matrix",
        "mature_findings",
        "controversies_or_uncertainties",
        "research_gaps",
        "recommended_reading_order",
        "candidate_research_questions",
        "evidence_index",
    ]
    return not any(synthesis.get(key) for key in list_keys)


def format_count_rows(rows: list[dict], label_key: str, limit: int = 8) -> list[str]:
    values = []
    for row in rows[:limit]:
        values.append(f"{row.get(label_key, 'Unknown')} ({row.get('paper_count', 0)} papers; {row.get('citation_count', 0)} citations)")
    return values


def bullets(values: list[str]) -> str:
    if not values:
        return "- Not enough evidence in the prepared inputs."
    return "\n".join(f"- {value}" for value in values)


def markdown_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "No records available."
    lines = [
        "| " + " | ".join(clean_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(clean_cell(value) for value in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def clean_cell(value) -> str:
    text = str(value if value is not None else "").replace("\n", " ")
    text = text.replace("|", "/")
    return re.sub(r"\s+", " ", text).strip()


def short_cell(value, limit: int = 180) -> str:
    text = clean_cell(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def normalize_title_ref(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title).casefold()).strip()


def first_string(values) -> str:
    if isinstance(values, str):
        return values
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value
    return ""


def first_dict(values) -> dict:
    if isinstance(values, dict):
        return values
    if isinstance(values, list):
        for value in values:
            if isinstance(value, dict):
                return value
    return {}


def keyword_summary(text: str, limit: int = 8) -> list[str]:
    stopwords = {
        "and", "the", "with", "for", "in", "of", "to", "a", "an",
        "studies", "research", "applications", "science",
    }
    counts = {}
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", text.casefold()):
        if token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def markdown_to_html(markdown: str, title: str = "Survey Report") -> str:
    body = []
    in_ul = False
    in_table = False
    table_rows = []

    def close_ul():
        nonlocal in_ul
        if in_ul:
            body.append("</ul>")
            in_ul = False

    def close_table():
        nonlocal in_table, table_rows
        if not in_table:
            return
        body.append("<table>")
        for index, row in enumerate(table_rows):
            tag = "th" if index == 0 else "td"
            if index == 1:
                continue
            body.append("<tr>" + "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in row) + "</tr>")
        body.append("</table>")
        in_table = False
        table_rows = []

    for line in markdown.splitlines():
        if line.startswith("| ") and line.endswith(" |"):
            close_ul()
            in_table = True
            table_rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        close_table()
        if line.startswith("# "):
            close_ul()
            body.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            close_ul()
            body.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            close_ul()
            body.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{inline_markdown(line[2:].strip())}</li>")
        elif not line.strip():
            close_ul()
        else:
            close_ul()
            body.append(f"<p>{inline_markdown(line.strip())}</p>")
    close_ul()
    close_table()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Georgia, 'Times New Roman', serif; line-height: 1.58; max-width: 1120px; margin: 40px auto; padding: 0 24px; color: #1f2933; }}
    h1, h2, h3 {{ font-family: Segoe UI, Arial, sans-serif; line-height: 1.25; }}
    h1 {{ font-size: 34px; border-bottom: 2px solid #1f2933; padding-bottom: 12px; }}
    h2 {{ margin-top: 34px; border-bottom: 1px solid #d9e2ec; padding-bottom: 6px; }}
    h3 {{ margin-top: 26px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; font-size: 14px; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 7px 9px; vertical-align: top; }}
    th {{ background: #f3f6f9; text-align: left; }}
    code {{ background: #f3f6f9; padding: 1px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
{chr(10).join(body)}
</body>
</html>
"""


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def relative_or_str(path: Path) -> str:
    return str(Path(path))


def run_from_args(args) -> int:
    builder = FinalSurveyReportBuilder(
        results_dir=Path(args.results_dir),
        agent_dir=Path(args.agent_dir) if getattr(args, "agent_dir", None) else None,
        reports_dir=Path(args.reports_dir) if getattr(args, "reports_dir", None) else None,
        out=Path(args.out) if getattr(args, "out", None) else None,
        html_out=Path(args.html_out) if getattr(args, "html_out", None) else None,
        title=getattr(args, "title", ""),
        max_domains=getattr(args, "max_domains", 10),
        max_papers_per_domain=getattr(args, "max_papers_per_domain", 8),
        max_recommended_papers=getattr(args, "max_recommended_papers", 12),
    )
    builder.build()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a final academic-style survey report from existing outputs.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--agent-dir")
    parser.add_argument("--reports-dir")
    parser.add_argument("--out")
    parser.add_argument("--html-out")
    parser.add_argument("--title", default="")
    parser.add_argument("--max-domains", type=int, default=10)
    parser.add_argument("--max-papers-per-domain", type=int, default=8)
    parser.add_argument("--max-recommended-papers", type=int, default=12)
    return parser


if __name__ == "__main__":
    raise SystemExit(run_from_args(build_parser().parse_args()))
