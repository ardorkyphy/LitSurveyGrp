from __future__ import annotations

from dataclasses import dataclass, field


STAGE_DISCOVERY = "discovery"
STAGE_ENRICHMENT = "enrichment"
STAGE_CLASSIFICATION = "classification"
STAGE_STATS = "stats"
STAGE_VISUALIZATION = "visualization"
STAGE_PDF_DOWNLOAD = "pdf_download"
STAGE_REFERENCE_ANALYSIS = "reference_analysis"
STAGE_AGENT_INPUT = "agent_input"
STAGE_PAPER_AGENTS = "paper_agents"
STAGE_DOMAIN_SYNTHESIS = "domain_synthesis"
STAGE_FINAL_REPORT = "final_report"

CORE_STAGES = {
    STAGE_DISCOVERY,
    STAGE_ENRICHMENT,
    STAGE_CLASSIFICATION,
    STAGE_STATS,
    STAGE_VISUALIZATION,
    STAGE_REFERENCE_ANALYSIS,
}

COMMAND_STAGES = CORE_STAGES | {
    STAGE_PDF_DOWNLOAD,
    STAGE_AGENT_INPUT,
    STAGE_PAPER_AGENTS,
    STAGE_DOMAIN_SYNTHESIS,
    STAGE_FINAL_REPORT,
}


@dataclass
class StageSetting:
    """Execution setting for one workflow stage."""

    enabled: bool = True
    mode: str = "default"

    def to_dict(self) -> dict:
        return {"enabled": bool(self.enabled), "mode": self.mode}


@dataclass
class StageControl:
    """Future-friendly stage controls shared by CLI and frontends."""

    settings: dict[str, StageSetting] = field(default_factory=dict)

    def is_enabled(self, stage: str, default: bool = True) -> bool:
        return self.settings.get(stage, StageSetting(default)).enabled

    def mode(self, stage: str, default: str = "default") -> str:
        return self.settings.get(stage, StageSetting(True, default)).mode

    def disable(self, stage: str) -> None:
        current = self.settings.get(stage, StageSetting())
        self.settings[stage] = StageSetting(enabled=False, mode=current.mode)

    def set_mode(self, stage: str, mode: str) -> None:
        current = self.settings.get(stage, StageSetting())
        self.settings[stage] = StageSetting(enabled=current.enabled, mode=mode)

    def to_dict(self) -> dict:
        return {stage: setting.to_dict() for stage, setting in sorted(self.settings.items())}

    @classmethod
    def from_values(
        cls,
        disabled: list[str] | None = None,
        modes: list[str] | None = None,
        allowed: set[str] | None = None,
    ) -> "StageControl":
        control = cls()
        for stage in disabled or []:
            normalized = normalize_stage_name(stage)
            if allowed is not None and normalized not in allowed:
                raise ValueError(f"unsupported stage: {stage}")
            control.disable(normalized)
        for value in modes or []:
            if "=" not in value:
                raise ValueError(f"stage mode must use stage=mode: {value}")
            stage, mode = value.split("=", 1)
            normalized = normalize_stage_name(stage)
            if allowed is not None and normalized not in allowed:
                raise ValueError(f"unsupported stage: {stage}")
            if not mode.strip():
                raise ValueError(f"stage mode cannot be empty: {value}")
            control.set_mode(normalized, mode.strip())
        return control


STAGE_ALIASES = {
    "download": STAGE_DISCOVERY,
    "metadata": STAGE_DISCOVERY,
    "metadata_pipeline": STAGE_DISCOVERY,
    "discover": STAGE_DISCOVERY,
    "enrich": STAGE_ENRICHMENT,
    "classify": STAGE_CLASSIFICATION,
    "visualize": STAGE_VISUALIZATION,
    "references": STAGE_REFERENCE_ANALYSIS,
    "pdf": STAGE_PDF_DOWNLOAD,
    "pdfs": STAGE_PDF_DOWNLOAD,
    "download_pdfs": STAGE_PDF_DOWNLOAD,
    "agents": STAGE_PAPER_AGENTS,
    "paper_reader_agent": STAGE_PAPER_AGENTS,
    "domain_synthesizer_agent": STAGE_DOMAIN_SYNTHESIS,
    "domain_agents": STAGE_DOMAIN_SYNTHESIS,
    "report": STAGE_FINAL_REPORT,
}


def normalize_stage_name(value: str) -> str:
    normalized = str(value or "").strip().replace("-", "_")
    return STAGE_ALIASES.get(normalized, normalized)

