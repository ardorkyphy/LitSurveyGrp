# -*- coding: utf-8 -*-
"""Paper-level research analysis agent.

This module consumes the generic packages produced by
``litsurveygrp prepare-agent-input`` and writes one structured analysis file per
paper. It is intentionally domain-neutral: all domain context comes from input
metadata, not from hardcoded taxonomies or biomedical/CS-specific prompts.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agents.llm_client import LLMClient, build_llm_client
from litsurveygrp.run_monitor import RunMonitor


PAPER_ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "research_problem": {"type": "string"},
        "background_gap": {"type": "string"},
        "study_object": {"type": "string"},
        "data_or_materials": {"type": "array", "items": {"type": "string"}},
        "methods": {"type": "array", "items": {"type": "string"}},
        "method_pipeline": {"type": "string"},
        "core_findings": {"type": "array", "items": {"type": "string"}},
        "evidence_type": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "reusable_resources": {"type": "array", "items": {"type": "string"}},
        "source_basis": {"type": "string", "enum": ["metadata_only", "abstract_only", "pdf_text"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "supporting_text": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "research_problem",
        "background_gap",
        "study_object",
        "data_or_materials",
        "methods",
        "method_pipeline",
        "core_findings",
        "evidence_type",
        "limitations",
        "open_questions",
        "reusable_resources",
        "source_basis",
        "confidence",
        "supporting_text",
    ],
}


PAPER_SYSTEM_PROMPT = """You are a domain-neutral literature review analyst.
Use only the supplied paper metadata, abstract, and extracted text. Do not add
field-specific assumptions that are not supported by the input. Extract the
research problem, method system, findings, limitations, and reusable resources
in a way that would be useful for a researcher entering this domain. Return JSON
that exactly matches the requested schema."""


@dataclass
class PaperReaderAgent:
    """Analyze every paper package under an agent-input root."""

    input_dir: Path
    provider: str = "dry-run"
    model: str = "gpt-4.1-mini"
    cache_dir: Path | None = None
    overwrite: bool = False
    llm_client: LLMClient | None = None
    monitor: RunMonitor | None = None

    def __post_init__(self) -> None:
        self.input_dir = Path(self.input_dir)
        self.cache_dir = Path(self.cache_dir) if self.cache_dir else None
        if self.llm_client is None:
            self.llm_client = build_llm_client(self.provider, self.cache_dir)

    def run(self) -> dict:
        domains = domain_dirs(self.input_dir)
        paper_paths = [
            (domain_dir, paper_path)
            for domain_dir in domains
            for paper_path in sorted((domain_dir / "papers").glob("*.json"))
        ]
        self.start_monitor(total=len(paper_paths), domain_count=len(domains))
        written = []
        skipped = []
        try:
            for index, (domain_dir, paper_path) in enumerate(paper_paths, start=1):
                analysis_dir = domain_dir / "paper_analysis"
                analysis_dir.mkdir(parents=True, exist_ok=True)
                out_path = analysis_dir / f"{paper_path.stem}.analysis.json"
                if out_path.exists() and not self.overwrite:
                    skipped.append(str(out_path))
                    self.update_monitor(
                        processed=index,
                        total=len(paper_paths),
                        current_item=f"{domain_dir.name}/{paper_path.stem}",
                        metrics={"written": len(written), "skipped": len(skipped)},
                    )
                    continue
                paper = read_json(paper_path)
                self.update_monitor(
                    processed=index - 1,
                    total=len(paper_paths),
                    current_item=paper.get("title") or f"{domain_dir.name}/{paper_path.stem}",
                    metrics={"domain": domain_dir.name, "written": len(written), "skipped": len(skipped)},
                )
                payload = self.build_payload(domain_dir, paper)
                result = self.llm_client.complete_json(
                    system=PAPER_SYSTEM_PROMPT,
                    user=json.dumps(payload, ensure_ascii=False, indent=2),
                    schema=PAPER_ANALYSIS_SCHEMA,
                    model=self.model,
                    cache_key=f"paper:{domain_dir.name}:{paper_path.stem}",
                )
                result = normalize_paper_analysis(result, payload["source_basis"])
                write_json(out_path, result)
                written.append(str(out_path))
            summary = {
                "input_dir": str(self.input_dir),
                "provider": self.provider,
                "model": self.model,
                "cache_dir": str(self.cache_dir or ""),
                "monitor_status": str(self.monitor.status_path) if self.monitor else "",
                "domain_count": len(domains),
                "written_count": len(written),
                "skipped_count": len(skipped),
                "written": written,
                "skipped": skipped,
            }
            write_json(self.input_dir / "paper_reader_summary.json", summary)
            self.update_monitor(
                processed=len(written) + len(skipped),
                total=len(paper_paths),
                current_item="",
                metrics={"written": len(written), "skipped": len(skipped)},
            )
            self.finish_monitor("completed", f"Paper reader analyzed {len(written)} papers; skipped {len(skipped)}")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"Paper reader failed: {exc}")
            raise

    def build_payload(self, domain_dir: Path, paper: dict) -> dict:
        text = ""
        text_path = paper.get("text_path") or ""
        if text_path:
            path = Path(text_path)
            if not path.is_absolute():
                path = domain_dir / text_path
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")

        source_basis = "metadata_only"
        if text:
            source_basis = "pdf_text"
        elif paper.get("abstract"):
            source_basis = "abstract_only"

        return {
            "task": "paper_research_analysis",
            "source_basis": source_basis,
            "paper": compact_paper_payload(paper),
            "extracted_text": text,
        }

    def start_monitor(self, total: int, domain_count: int) -> None:
        if self.monitor:
            self.monitor.start(
                "LitSurveyGrp paper reader agent",
                "Analyzing selected papers for research problems and methods",
                metrics={
                    "input_dir": str(self.input_dir),
                    "provider": self.provider,
                    "model": self.model,
                    "cache_dir": str(self.cache_dir or ""),
                    "domains": domain_count,
                    "papers": total,
                },
            )
            self.monitor.update(
                stage="paper_reader",
                message="Starting paper-level analysis",
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
                stage="paper_reader",
                message="Analyzing paper",
                processed=processed,
                total=total,
                current_item=current_item,
                metrics=metrics,
            )

    def finish_monitor(self, status: str, message: str) -> None:
        if self.monitor:
            self.monitor.finish(status, message)


def compact_paper_payload(paper: dict) -> dict:
    keys = [
        "paper_id",
        "title",
        "doi",
        "journal",
        "year",
        "publish_date",
        "authors",
        "institutions",
        "abstract",
        "article_type",
        "domain",
        "classification_source",
        "classification_taxonomy",
        "classification_source_label",
        "authoritative_topics",
        "citation_count",
        "research_value_score",
        "value_reason",
        "journal_tier",
    ]
    return {key: paper.get(key, "" if key not in {"authors", "institutions", "authoritative_topics"} else []) for key in keys}


def normalize_paper_analysis(result: dict, source_basis: str) -> dict:
    normalized = dict(result or {})
    defaults = {
        "research_problem": "",
        "background_gap": "",
        "study_object": "",
        "data_or_materials": [],
        "methods": [],
        "method_pipeline": "",
        "core_findings": [],
        "evidence_type": "",
        "limitations": [],
        "open_questions": [],
        "reusable_resources": [],
        "source_basis": source_basis,
        "confidence": "low",
        "supporting_text": [],
    }
    for key, value in defaults.items():
        normalized.setdefault(key, value)
    if normalized.get("source_basis") not in {"metadata_only", "abstract_only", "pdf_text"}:
        normalized["source_basis"] = source_basis
    if normalized.get("confidence") not in {"low", "medium", "high"}:
        normalized["confidence"] = "low"
    for key in [
        "data_or_materials",
        "methods",
        "core_findings",
        "limitations",
        "open_questions",
        "reusable_resources",
        "supporting_text",
    ]:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    return normalized


def domain_dirs(input_dir: Path) -> list[Path]:
    input_dir = Path(input_dir)
    return [
        path
        for path in sorted(input_dir.glob("domain_*"))
        if path.is_dir() and (path / "domain_manifest.json").exists() and (path / "papers").exists()
    ]


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def default_monitor_dir(input_dir: Path) -> Path:
    return Path(input_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze packaged papers with a replaceable LLM client.")
    parser.add_argument("--input-dir", required=True, help="agent input root produced by prepare-agent-input")
    parser.add_argument("--provider", default="dry-run", choices=["dry-run", "openai"])
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--cache-dir", help="directory for prompt/response cache")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--monitor-dir", help="directory for run_monitor.html and run_status.json; defaults to input-dir")
    parser.add_argument("--no-monitor", action="store_true", help="do not write monitor files for this agent")
    return parser


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor = RunMonitor(Path(getattr(args, "monitor_dir", "") or default_monitor_dir(Path(args.input_dir))))
    agent = PaperReaderAgent(
        input_dir=Path(args.input_dir),
        provider=args.provider,
        model=args.model,
        cache_dir=Path(args.cache_dir) if getattr(args, "cache_dir", None) else None,
        overwrite=getattr(args, "overwrite", False),
        monitor=monitor,
    )
    agent.run()
    return 0


def main() -> int:
    return run_from_args(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
