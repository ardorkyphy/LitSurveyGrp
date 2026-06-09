# -*- coding: utf-8 -*-
"""Paper-level research analysis agent.

This module consumes the generic packages produced by
``litsurveygrp prepare-agent-input`` and writes one structured analysis file per
paper. It is intentionally domain-neutral: all domain context comes from input
metadata, not from hardcoded taxonomies or biomedical/CS-specific prompts.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from agents.llm_client import LLMClient, build_llm_client
from agents.llm_client import default_model_for_provider
from agents.validation import require_non_empty_strings, unsupported_supporting_text, validate_schema
from agents.evidence import build_evidence_bundle, selected_text
from litsurveygrp.analysis_paths import AnalysisLayout, major_domain_name, subdomain_name
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
in a way that would be useful for a researcher entering this domain. When
evidence chunks are supplied, use them as the primary source and prefer exact
phrasing from those chunks for support. Return JSON that exactly matches the
requested schema. Every supporting_text item must be an exact contiguous
substring copied from the supplied abstract, extracted text, or evidence chunks.
If no exact source sentence is available, return an empty supporting_text list."""


@dataclass
class PaperReaderAgent:
    """Analyze every paper package under an agent-input root."""

    input_dir: Path
    results_dir: Path | None = None
    reports_dir: Path | None = None
    provider: str = "dry-run"
    model: str = ""
    cache_dir: Path | None = None
    base_url: str = ""
    overwrite: bool = False
    workers: int = 1
    input_mode: str = "evidence-chunks"
    max_chunks_per_paper: int = 12
    max_chunk_chars: int = 2200
    llm_client: LLMClient | None = None
    monitor: RunMonitor | None = None

    def __post_init__(self) -> None:
        self.input_dir = Path(self.input_dir)
        self.results_dir = Path(self.results_dir) if self.results_dir else self.input_dir.parent / "results"
        self.reports_dir = Path(self.reports_dir) if self.reports_dir else self.results_dir.parent / "reports"
        self.cache_dir = Path(self.cache_dir) if self.cache_dir else None
        self.workers = max(1, int(self.workers or 1))
        if self.input_mode not in {"evidence-chunks", "full-text"}:
            raise ValueError(f"unsupported paper agent input mode: {self.input_mode}")
        self.max_chunks_per_paper = max(1, int(self.max_chunks_per_paper or 1))
        self.max_chunk_chars = max(400, int(self.max_chunk_chars or 2200))
        self.model = self.model or default_model_for_provider(self.provider)
        if self.llm_client is None:
            self.llm_client = build_llm_client(
                self.provider,
                self.cache_dir,
                base_url=self.base_url or None,
            )

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
        failed = []
        try:
            pending = []
            processed = 0
            for domain_dir, paper_path in paper_paths:
                analysis_dir = self.analysis_dir_for_domain(domain_dir)
                analysis_dir.mkdir(parents=True, exist_ok=True)
                out_path = analysis_dir / f"{paper_path.stem}.analysis.json"
                error_path = analysis_dir / f"{paper_path.stem}.analysis.error.json"
                if out_path.exists() and not self.overwrite:
                    skipped.append(str(out_path))
                    processed += 1
                    self.update_monitor(
                        processed=processed,
                        total=len(paper_paths),
                        current_item=f"{domain_dir.name}/{paper_path.stem}",
                        metrics={"written": len(written), "skipped": len(skipped), "workers": self.workers},
                    )
                    continue
                pending.append((domain_dir, paper_path, out_path, error_path))

            if self.workers == 1:
                for domain_dir, paper_path, out_path, error_path in pending:
                    paper = read_json(paper_path)
                    self.update_monitor(
                        processed=processed,
                        total=len(paper_paths),
                        current_item=paper.get("title") or f"{domain_dir.name}/{paper_path.stem}",
                        metrics={
                            "domain": domain_dir.name,
                            "written": len(written),
                            "skipped": len(skipped),
                            "failed": len(failed),
                            "workers": self.workers,
                            "input_mode": self.input_mode,
                        },
                    )
                    status, path = self.analyze_one(domain_dir, paper_path, out_path, error_path, paper)
                    if status == "written":
                        written.append(path)
                    else:
                        failed.append(path)
                    processed += 1
                    self.update_monitor(
                        processed=processed,
                        total=len(paper_paths),
                        current_item=paper.get("title") or f"{domain_dir.name}/{paper_path.stem}",
                        metrics={"written": len(written), "skipped": len(skipped), "failed": len(failed), "workers": self.workers},
                    )
            else:
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    futures = {
                        executor.submit(self.analyze_one, domain_dir, paper_path, out_path, error_path): (
                            domain_dir,
                            paper_path,
                        )
                        for domain_dir, paper_path, out_path, error_path in pending
                    }
                    for future in as_completed(futures):
                        domain_dir, paper_path = futures[future]
                        status, path = future.result()
                        if status == "written":
                            written.append(path)
                        else:
                            failed.append(path)
                        processed += 1
                        self.update_monitor(
                            processed=processed,
                            total=len(paper_paths),
                            current_item=f"{domain_dir.name}/{paper_path.stem}",
                            metrics={"written": len(written), "skipped": len(skipped), "failed": len(failed), "workers": self.workers, "input_mode": self.input_mode},
                        )
            summary = {
                "input_dir": str(self.input_dir),
                "provider": self.provider,
                "model": self.model,
                "cache_dir": str(self.cache_dir or ""),
                "workers": self.workers,
                "input_mode": self.input_mode,
                "max_chunks_per_paper": self.max_chunks_per_paper,
                "max_chunk_chars": self.max_chunk_chars,
                "monitor_status": str(self.monitor.status_path) if self.monitor else "",
                "domain_count": len(domains),
                "written_count": len(written),
                "skipped_count": len(skipped),
                "failed_count": len(failed),
                "written": written,
                "skipped": skipped,
                "failed": failed,
            }
            self.write_summary(summary, domains)
            self.update_monitor(
                processed=len(written) + len(skipped) + len(failed),
                total=len(paper_paths),
                current_item="",
                metrics={"written": len(written), "skipped": len(skipped), "failed": len(failed)},
            )
            self.finish_monitor("completed", f"Paper reader analyzed {len(written)} papers; skipped {len(skipped)}; failed {len(failed)}")
            return summary
        except Exception as exc:
            self.finish_monitor("failed", f"Paper reader failed: {exc}")
            raise

    def analyze_one(
        self,
        domain_dir: Path,
        paper_path: Path,
        out_path: Path,
        error_path: Path,
        paper: dict | None = None,
    ) -> tuple[str, str]:
        paper = paper or read_json(paper_path)
        payload = self.build_payload(domain_dir, paper)
        try:
            result = self.llm_client.complete_json(
                system=PAPER_SYSTEM_PROMPT,
                user=json.dumps(payload, ensure_ascii=False, indent=2),
                schema=PAPER_ANALYSIS_SCHEMA,
                model=self.model,
                cache_key=f"paper:{self.input_mode}:{domain_dir.name}:{paper_path.stem}",
            )
            result = normalize_paper_analysis(result, payload["source_basis"])
            validation_errors = validate_paper_analysis(result, payload, paper)
            validation_warnings = []
            unsupported = result.pop("unsupported_supporting_text", [])
            if unsupported:
                validation_warnings.extend([f"$.supporting_text: removed unsupported snippet {index + 1}" for index, _ in enumerate(unsupported)])
                result["supporting_text"] = [
                    snippet for snippet in result.get("supporting_text", [])
                    if snippet not in unsupported
                ]
            if validation_errors:
                error_record = {
                    "paper_path": str(paper_path),
                    "title": paper.get("title", ""),
                    "validation_status": "invalid",
                    "validation_errors": validation_errors,
                    "analysis": result,
                }
                write_json(error_path, error_record)
                if out_path.exists():
                    out_path.unlink()
                return "failed", str(error_path)
            result["validation_status"] = "valid"
            result["validation_errors"] = []
            result["validation_warnings"] = validation_warnings
            result["unsupported_supporting_text"] = []
            if payload.get("evidence"):
                result["evidence_coverage"] = payload["evidence"].get("coverage", {})
                result["evidence_chunks"] = [
                    {
                        "chunk_id": chunk.get("chunk_id", ""),
                        "section": chunk.get("section", ""),
                        "score": chunk.get("score", 0),
                        "reasons": chunk.get("reasons", []),
                        "lexical_score": chunk.get("lexical_score", 0),
                        "embedding_score": chunk.get("embedding_score", 0),
                        "rerank_score": chunk.get("rerank_score", 0),
                        "semantic_purpose": chunk.get("semantic_purpose", ""),
                        "selection_method": chunk.get("selection_method", ""),
                        "models": chunk.get("models", {}),
                    }
                    for chunk in payload["evidence"].get("selected_chunks", [])
                ]
            if error_path.exists():
                error_path.unlink()
            write_json(out_path, result)
            return "written", str(out_path)
        except Exception as exc:
            write_json(
                error_path,
                {
                    "paper_path": str(paper_path),
                    "title": paper.get("title", ""),
                    "validation_status": "invalid",
                    "validation_errors": [f"agent_failed: {exc}"],
                },
            )
            return "failed", str(error_path)

    def build_payload(self, domain_dir: Path, paper: dict) -> dict:
        text = ""
        text_path = paper.get("text_path") or ""
        if text_path:
            path = Path(text_path)
            if not path.is_absolute():
                path = domain_dir / text_path
            if not path.exists():
                fallback = Path(text_path)
                if fallback.exists():
                    path = fallback
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")

        source_basis = "metadata_only"
        if text:
            source_basis = "pdf_text"
        elif paper.get("abstract"):
            source_basis = "abstract_only"

        payload = {
            "task": "paper_research_analysis",
            "source_basis": source_basis,
            "paper": compact_paper_payload(paper),
        }
        if self.input_mode == "full-text":
            payload["extracted_text"] = text
            return payload
        evidence = build_evidence_bundle(
            paper_id=paper.get("paper_id") or "paper",
            abstract=paper.get("abstract", ""),
            text=text,
            max_chunks=self.max_chunks_per_paper,
            chunk_chars=self.max_chunk_chars,
        )
        payload["evidence"] = evidence
        payload["extracted_text"] = ""
        return payload

    def analysis_dir_for_domain(self, domain_dir: Path) -> Path:
        manifest = read_json(domain_dir / "domain_manifest.json")
        layout = AnalysisLayout(
            papers_dir=self.results_dir.parent / "papers",
            results_dir=self.results_dir,
            reports_dir=self.reports_dir,
            major_domain=manifest.get("major_domain") or major_domain_name(manifest.get("domain_name", "")),
            subdomain=manifest.get("subdomain_dir") or subdomain_name(manifest.get("domain_name", ""), domain_dir.name),
        )
        return layout.analysis_domain_dir

    def write_summary(self, summary: dict, domains: list[Path]) -> None:
        for domain_dir in domains:
            domain_summary = dict(summary)
            domain_summary["domain_dir"] = str(domain_dir)
            write_json(self.analysis_dir_for_domain(domain_dir) / "paper_reader_summary.json", domain_summary)

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
                    "workers": self.workers,
                    "input_mode": self.input_mode,
                    "max_chunks_per_paper": self.max_chunks_per_paper,
                    "max_chunk_chars": self.max_chunk_chars,
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


def validate_paper_analysis(result: dict, payload: dict, paper: dict) -> list[str]:
    errors = validate_schema(result, PAPER_ANALYSIS_SCHEMA)
    errors.extend(require_non_empty_strings(result, ["research_problem", "source_basis", "confidence"]))
    evidence_text = selected_text(payload.get("evidence") or {})
    basis_text = "\n".join([
        str((paper or {}).get("abstract") or ""),
        str(payload.get("extracted_text") or ""),
        evidence_text,
    ])
    unsupported = unsupported_supporting_text(result, basis_text)
    result["unsupported_supporting_text"] = unsupported or []
    return errors


def domain_dirs(input_dir: Path) -> list[Path]:
    input_dir = Path(input_dir)
    legacy = [
        path
        for path in sorted(input_dir.glob("domain_*"))
        if path.is_dir() and (path / "domain_manifest.json").exists() and (path / "papers").exists()
    ]
    discovered = [
        path.parent
        for path in sorted(input_dir.rglob("domain_manifest.json"))
        if (path.parent / "papers").exists()
    ]
    seen = set()
    domains = []
    for path in [*legacy, *discovered]:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            domains.append(path)
    return domains


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
    parser.add_argument("--results-dir", help="results root for domain analysis artifacts; defaults to sibling results")
    parser.add_argument("--reports-dir", help="reports root; defaults to sibling reports")
    parser.add_argument("--provider", default="dry-run", choices=["dry-run", "openai", "deepseek"])
    parser.add_argument("--model", default="", help="LLM model; defaults by provider")
    parser.add_argument("--base-url", default="", help="optional OpenAI-compatible base URL override")
    parser.add_argument("--cache-dir", help="directory for prompt/response cache")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--workers", type=int, default=1, help="parallel LLM requests for paper analysis")
    parser.add_argument("--input-mode", default="evidence-chunks", choices=["evidence-chunks", "full-text"])
    parser.add_argument("--max-chunks-per-paper", type=int, default=12)
    parser.add_argument("--max-chunk-chars", type=int, default=2200)
    parser.add_argument("--monitor-dir", help="directory for run_monitor.html and run_status.json; defaults to input-dir")
    parser.add_argument("--no-monitor", action="store_true", help="do not write monitor files for this agent")
    return parser


def run_from_args(args) -> int:
    monitor = None
    if not getattr(args, "no_monitor", False):
        monitor = RunMonitor(Path(getattr(args, "monitor_dir", "") or default_monitor_dir(Path(args.input_dir))))
    agent = PaperReaderAgent(
        input_dir=Path(args.input_dir),
        results_dir=Path(args.results_dir) if getattr(args, "results_dir", None) else None,
        reports_dir=Path(args.reports_dir) if getattr(args, "reports_dir", None) else None,
        provider=args.provider,
        model=args.model,
        cache_dir=Path(args.cache_dir) if getattr(args, "cache_dir", None) else None,
        base_url=getattr(args, "base_url", ""),
        overwrite=getattr(args, "overwrite", False),
        workers=getattr(args, "workers", 1),
        input_mode=getattr(args, "input_mode", "evidence-chunks"),
        max_chunks_per_paper=getattr(args, "max_chunks_per_paper", 12),
        max_chunk_chars=getattr(args, "max_chunk_chars", 2200),
        monitor=monitor,
    )
    agent.run()
    return 0


def main() -> int:
    return run_from_args(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
