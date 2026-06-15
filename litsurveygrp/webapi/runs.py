from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from litsurveygrp.multi_journal_downloader import list_supported_journals
from litsurveygrp.stage_control import COMMAND_STAGES
from litsurveygrp.webapi.schemas import ProcessStartResponse, RunCreateRequest, RunFile, RunSummary, StageOption


STAGE_LABELS = {
    "discovery": "Discovery",
    "enrichment": "Metadata Enrichment",
    "classification": "Classification",
    "stats": "Statistics",
    "visualization": "Dashboard",
    "reference_analysis": "Reference Analysis",
    "pdf_download": "PDF Download",
    "agent_input": "Agent Input",
    "paper_agents": "Paper Agents",
    "domain_synthesis": "Domain Synthesis",
    "final_report": "Final Report",
}


def stage_schema() -> list[StageOption]:
    ordered = [
        "discovery",
        "enrichment",
        "classification",
        "stats",
        "visualization",
        "pdf_download",
        "reference_analysis",
        "agent_input",
        "paper_agents",
        "domain_synthesis",
        "final_report",
    ]
    return [
        StageOption(key=stage, label=STAGE_LABELS.get(stage, stage.replace("_", " ").title()))
        for stage in ordered
        if stage in COMMAND_STAGES
    ]


class RunStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def list_runs(self) -> list[RunSummary]:
        runs = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_dir():
                continue
            summary = self.summary_for(path)
            if summary:
                runs.append(summary)
        return runs

    def summary_for(self, path: Path) -> RunSummary | None:
        path = Path(path)
        if not path.exists() or not path.is_dir():
            return None
        status = self.read_status(path)
        report_html = first_existing(path, ["reports/*/data/final_survey_report.html"])
        monitor_html = first_existing(path, ["reports/*/data/run_monitor.html"])
        return RunSummary(
            id=path.name,
            path=str(path),
            status=status.get("status", "unknown"),
            stage=status.get("stage", ""),
            message=status.get("message", ""),
            updated_at=status.get("updated_at", ""),
            report_html=str(report_html or ""),
            monitor_html=str(monitor_html or ""),
        )

    def resolve_run(self, run_id: str) -> Path:
        candidate = (self.root / run_id).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("run path escapes run root")
        return candidate

    def read_status(self, path: Path) -> dict[str, Any]:
        status_path = first_existing(path, ["reports/*/data/run_status.json", "run_status.json"])
        if not status_path:
            return {}
        return read_json(status_path, {})

    def files_for(self, path: Path) -> list[RunFile]:
        files = []
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() not in {".json", ".csv", ".html", ".md", ".pdf"}:
                continue
            files.append(RunFile(
                name=item.name,
                path=str(item),
                kind=item.suffix.lower().lstrip("."),
                size=item.stat().st_size,
            ))
        return sorted(files, key=lambda item: item.path)

    def manifest_for(self, path: Path, name: str = "classified_manifest.json") -> list[dict[str, Any]]:
        manifest_path = first_existing(path, [f"reports/*/data/{name}", f"**/{name}"])
        if not manifest_path:
            return []
        data = read_json(manifest_path, [])
        return data if isinstance(data, list) else []

    def delete_run(self, run_id: str) -> None:
        path = self.resolve_run(run_id)
        if path.exists():
            shutil.rmtree(path)


class SurveyRunner:
    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)

    def build_command(self, request: RunCreateRequest) -> list[str]:
        command = [sys.executable, "-m", "litsurveygrp", "survey", "--out", request.out, "--preset", request.preset]
        append_value(command, "--query", request.query)
        for journal in request.journal:
            append_value(command, "--journal", journal)
        for keyword in request.keyword:
            append_value(command, "--keyword", keyword)
        append_value(command, "--limit", request.limit)
        append_value(command, "--per-journal-limit", request.per_journal_limit)
        append_value(command, "--pdfs", request.pdfs)
        append_value(command, "--domains", request.domains)
        append_value(command, "--papers-per-domain", request.papers_per_domain)
        append_value(command, "--model-provider", request.model_provider)
        append_value(command, "--model", request.model)
        append_value(command, "--workers", request.workers)
        append_value(command, "--title", request.title)
        for option in request.stage_control.values():
            if not option.enabled:
                append_value(command, "--skip-stage", option.key)
            if option.mode and option.mode != "default":
                append_value(command, "--stage-mode", f"{option.key}={option.mode}")
        return command

    def start(self, request: RunCreateRequest) -> ProcessStartResponse:
        command = self.build_command(request)
        process = subprocess.Popen(
            command,
            cwd=str(self.cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return ProcessStartResponse(
            id=Path(request.out).name,
            path=str((self.cwd / request.out).resolve()),
            pid=process.pid,
            command=command,
        )


def journal_schema() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "name": config.name,
            "provider": config.provider,
            "group": config.group,
            "issn": config.issn,
        }
        for key, config in list_supported_journals()
    ]


def append_value(command: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    command.extend([flag, str(value)])


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def first_existing(root: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.exists():
                return path
    return None
