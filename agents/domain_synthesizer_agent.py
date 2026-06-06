# -*- coding: utf-8 -*-
"""Domain-level synthesis agent for generic literature survey packages."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agents.llm_client import LLMClient, build_llm_client
from agents.llm_client import default_model_for_provider
from agents.paper_reader_agent import domain_dirs, read_json, write_json
from agents.validation import require_non_empty_strings, unknown_evidence_papers, validate_schema
from litsurveygrp.run_monitor import RunMonitor


DOMAIN_SYNTHESIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "domain": {"type": "string"},
        "one_sentence_summary": {"type": "string"},
        "core_problem_system": {"type": "array", "items": {"type": "string"}},
        "method_system": {"type": "array", "items": {"type": "string"}},
        "problem_method_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "problem": {"type": "string"},
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "representative_papers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["problem", "methods", "representative_papers"],
            },
        },
        "mature_findings": {"type": "array", "items": {"type": "string"}},
        "controversies_or_uncertainties": {"type": "array", "items": {"type": "string"}},
        "research_gaps": {"type": "array", "items": {"type": "string"}},
        "recommended_reading_order": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["title", "reason"],
            },
        },
        "candidate_research_questions": {"type": "array", "items": {"type": "string"}},
        "evidence_index": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "papers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "papers"],
            },
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "domain",
        "one_sentence_summary",
        "core_problem_system",
        "method_system",
        "problem_method_matrix",
        "mature_findings",
        "controversies_or_uncertainties",
        "research_gaps",
        "recommended_reading_order",
        "candidate_research_questions",
        "evidence_index",
        "confidence",
    ],
}


DOMAIN_SYSTEM_PROMPT = """You are a domain-neutral literature review synthesizer.
Use only the supplied domain manifest and paper-level analyses. Build a compact
research map: problems, methods, findings, uncertainties, gaps, reading order,
and candidate research questions. Do not assume a biomedical, computer science,
or social science ontology unless it is present in the input. Return JSON that
exactly matches the requested schema."""


@dataclass
class DomainSynthesizerAgent:
    """Synthesize per-domain paper analyses into research maps."""

    input_dir: Path
    provider: str = "dry-run"
    model: str = ""
    cache_dir: Path | None = None
    base_url: str = ""
    overwrite: bool = False
    llm_client: LLMClient | None = None
    monitor: RunMonitor | None = None

    def __post_init__(self) -> None:
        self.input_dir = Path(self.input_dir)
        self.cache_dir = Path(self.cache_dir) if self.cache_dir else None
        self.model = self.model or default_model_for_provider(self.provider)
        if self.llm_client is None:
            self.llm_client = build_llm_client(
                self.provider,
                self.cache_dir,
                base_url=self.base_url or None,
            )

    def run(self) -> dict:
        domains = domain_dirs(self.input_dir)
        self.start_monitor(total=len(domains))
        written = []
        skipped = []
        failed = []
        try:
            for index, domain_dir in enumerate(domains, start=1):
                out_path = domain_dir / "domain_synthesis.json"
                error_path = domain_dir / "domain_synthesis.error.json"
                report_path = domain_dir / "domain_report.md"
                if out_path.exists() and report_path.exists() and not self.overwrite:
                    skipped.append(str(out_path))
                    self.update_monitor(
                        processed=index,
                        total=len(domains),
                        current_item=domain_dir.name,
                        metrics={"written": len(written), "skipped": len(skipped)},
                    )
                    continue

                payload = self.build_payload(domain_dir)
                self.update_monitor(
                    processed=index - 1,
                    total=len(domains),
                    current_item=payload["domain"]["domain_name"] or domain_dir.name,
                    metrics={
                        "paper_analyses": len(payload["paper_analyses"]),
                        "written": len(written),
                        "skipped": len(skipped),
                    },
                )
                try:
                    result = self.llm_client.complete_json(
                        system=DOMAIN_SYSTEM_PROMPT,
                        user=json.dumps(payload, ensure_ascii=False, indent=2),
                        schema=DOMAIN_SYNTHESIS_SCHEMA,
                        model=self.model,
                        cache_key=f"domain:{domain_dir.name}",
                    )
                    result = normalize_domain_synthesis(result, payload["domain"]["domain_name"])
                    validation_errors = validate_domain_synthesis(result, payload)
                    if validation_errors:
                        write_json(
                            error_path,
                            {
                                "domain_dir": str(domain_dir),
                                "domain": payload["domain"]["domain_name"],
                                "validation_status": "invalid",
                                "validation_errors": validation_errors,
                                "synthesis": result,
                            },
                        )
                        if out_path.exists():
                            out_path.unlink()
                        if report_path.exists():
                            report_path.unlink()
                        failed.append(str(error_path))
                        continue
                    result["validation_status"] = "valid"
                    result["validation_errors"] = []
                    result["unknown_evidence_papers"] = []
                    if error_path.exists():
                        error_path.unlink()
                    write_json(out_path, result)
                    report_path.write_text(render_domain_report(result), encoding="utf-8")
                    written.append(str(out_path))
                except Exception as exc:
                    write_json(
                        error_path,
                        {
                            "domain_dir": str(domain_dir),
                            "domain": payload["domain"]["domain_name"],
                            "validation_status": "invalid",
                            "validation_errors": [f"agent_failed: {exc}"],
                        },
                    )
                    failed.append(str(error_path))

            summary = {
                "input_dir": str(self.input_dir),
                "provider": self.provider,
                "model": self.model,
                "cache_dir": str(self.cache_dir or ""),
                "monitor_status": str(self.monitor.status_path) if self.monitor else "",
                "domain_count": len(domains),
                "written_count": len(written),
                "skipped_count": len(skipped),
                "failed_count": len(failed),
                "written": written,
                "skipped": skipped,
                "failed": failed,
            }
            write_json(self.input_dir / "domain_synthesizer_summary.json", summary)
            self.update_monitor(
                processed=len(written) + len(skipped) + len(failed),
                total=len(domains),
                current_item="",
                metrics={"written": len(written), "skipped": len(skipped), "failed": len(failed)},
            )
            self.finish_monitor("completed", f"Domain synthesizer wrote {len(written)} domains; skipped {len(skipped)}; failed {len(failed)}")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"Domain synthesizer failed: {exc}")
            raise

    def build_payload(self, domain_dir: Path) -> dict:
        domain_manifest = read_json(domain_dir / "domain_manifest.json")
        analyses = []
        analysis_dir = domain_dir / "paper_analysis"
        for analysis_path in sorted(analysis_dir.glob("*.analysis.json")):
            paper_path = domain_dir / "papers" / analysis_path.name.replace(".analysis.json", ".json")
            paper = read_json(paper_path) if paper_path.exists() else {}
            analyses.append({
                "paper_id": paper.get("paper_id") or analysis_path.stem.replace(".analysis", ""),
                "title": paper.get("title", ""),
                "doi": paper.get("doi", ""),
                "year": paper.get("year", ""),
                "journal": paper.get("journal", ""),
                "research_value_score": paper.get("research_value_score", 0.0),
                "analysis": read_json(analysis_path),
            })
        return {
            "task": "domain_research_synthesis",
            "domain": {
                "domain_id": domain_manifest.get("domain_id", domain_dir.name),
                "domain_name": domain_manifest.get("domain_name", ""),
                "taxonomy_source": domain_manifest.get("taxonomy_source", ""),
                "paper_count": domain_manifest.get("paper_count", 0),
                "selected_paper_count": domain_manifest.get("selected_paper_count", len(analyses)),
                "citation_count": domain_manifest.get("citation_count", 0),
            },
            "paper_analyses": analyses,
        }

    def start_monitor(self, total: int) -> None:
        if self.monitor:
            self.monitor.start(
                "LitSurveyGrp domain synthesizer agent",
                "Synthesizing paper analyses into domain research maps",
                metrics={
                    "input_dir": str(self.input_dir),
                    "provider": self.provider,
                    "model": self.model,
                    "cache_dir": str(self.cache_dir or ""),
                    "domains": total,
                },
            )
            self.monitor.update(
                stage="domain_synthesis",
                message="Starting domain-level synthesis",
                processed=0,
                total=total,
            )

    def update_monitor(
        self,
        processed: int,
        total: int,
        current_item: str,
        metrics: dict | None = None,
    ) -> None:
        if self.monitor:
            self.monitor.update(
                stage="domain_synthesis",
                message="Synthesizing domain",
                processed=processed,
                total=total,
                current_item=current_item,
                metrics=metrics,
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def normalize_domain_synthesis(result: dict, domain_name: str) -> dict:
    normalized = dict(result or {})
    defaults = {
        "domain": domain_name,
        "one_sentence_summary": "",
        "core_problem_system": [],
        "method_system": [],
        "problem_method_matrix": [],
        "mature_findings": [],
        "controversies_or_uncertainties": [],
        "research_gaps": [],
        "recommended_reading_order": [],
        "candidate_research_questions": [],
        "evidence_index": [],
        "confidence": "low",
    }
    for key, value in defaults.items():
        normalized.setdefault(key, value)
    if normalized.get("confidence") not in {"low", "medium", "high"}:
        normalized["confidence"] = "low"
    for key in [
        "core_problem_system",
        "method_system",
        "problem_method_matrix",
        "mature_findings",
        "controversies_or_uncertainties",
        "research_gaps",
        "recommended_reading_order",
        "candidate_research_questions",
        "evidence_index",
    ]:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    return normalized


def validate_domain_synthesis(result: dict, payload: dict) -> list[str]:
    errors = validate_schema(result, DOMAIN_SYNTHESIS_SCHEMA)
    errors.extend(require_non_empty_strings(result, ["domain", "one_sentence_summary", "confidence"]))
    known_titles = {
        item.get("title", "")
        for item in payload.get("paper_analyses") or []
        if isinstance(item, dict)
    }
    unknown = unknown_evidence_papers(result, known_titles)
    if unknown:
        result["unknown_evidence_papers"] = unknown
        errors.extend([f"$.evidence_index: unknown paper title {title!r}" for title in unknown])
    else:
        result["unknown_evidence_papers"] = []
    return errors


def render_domain_report(synthesis: dict) -> str:
    lines = [
        f"# {synthesis.get('domain') or 'Domain'}",
        "",
        synthesis.get("one_sentence_summary", ""),
        "",
    ]
    sections = [
        ("Core Problem System", "core_problem_system"),
        ("Method System", "method_system"),
        ("Mature Findings", "mature_findings"),
        ("Controversies Or Uncertainties", "controversies_or_uncertainties"),
        ("Research Gaps", "research_gaps"),
        ("Candidate Research Questions", "candidate_research_questions"),
    ]
    for title, key in sections:
        lines.extend([f"## {title}", ""])
        values = synthesis.get(key) or []
        if values:
            lines.extend([f"- {value}" for value in values])
        else:
            lines.append("- Not enough evidence in the prepared inputs.")
        lines.append("")

    lines.extend(["## Recommended Reading Order", ""])
    reading = synthesis.get("recommended_reading_order") or []
    if reading:
        for item in reading:
            if isinstance(item, dict):
                lines.append(f"- {item.get('title', '')}: {item.get('reason', '')}".rstrip())
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- Not enough evidence in the prepared inputs.")
    lines.extend(["", f"Confidence: {synthesis.get('confidence', 'low')}", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthesize paper analyses into per-domain research maps.")
    parser.add_argument("--input-dir", required=True, help="agent input root produced by prepare-agent-input")
    parser.add_argument("--provider", default="dry-run", choices=["dry-run", "openai", "deepseek"])
    parser.add_argument("--model", default="", help="LLM model; defaults by provider")
    parser.add_argument("--base-url", default="", help="optional OpenAI-compatible base URL override")
    parser.add_argument("--cache-dir", help="directory for prompt/response cache")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--monitor-dir", help="directory for run_monitor.html and run_status.json; defaults to input-dir")
    parser.add_argument("--no-monitor", action="store_true", help="do not write monitor files for this agent")
    return parser


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor = RunMonitor(Path(getattr(args, "monitor_dir", "") or args.input_dir))
    agent = DomainSynthesizerAgent(
        input_dir=Path(args.input_dir),
        provider=args.provider,
        model=args.model,
        cache_dir=Path(args.cache_dir) if getattr(args, "cache_dir", None) else None,
        base_url=getattr(args, "base_url", ""),
        overwrite=getattr(args, "overwrite", False),
        monitor=monitor,
    )
    agent.run()
    return 0


def main() -> int:
    return run_from_args(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
