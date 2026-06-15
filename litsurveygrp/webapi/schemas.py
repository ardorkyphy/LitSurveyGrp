from __future__ import annotations

from pydantic import BaseModel, Field


class StageOption(BaseModel):
    key: str
    label: str
    enabled: bool = True
    mode: str = "default"
    modes: list[str] = Field(default_factory=lambda: ["default"])


class RunCreateRequest(BaseModel):
    out: str
    query: str = ""
    journal: list[str] = Field(default_factory=list)
    keyword: list[str] = Field(default_factory=list)
    preset: str = "balanced"
    limit: int | None = None
    per_journal_limit: int | None = None
    pdfs: int | None = None
    domains: int | None = None
    papers_per_domain: int | None = None
    model_provider: str | None = None
    model: str | None = None
    workers: int | None = None
    title: str = ""
    stage_control: dict[str, StageOption] = Field(default_factory=dict)


class RunSummary(BaseModel):
    id: str
    path: str
    status: str = "unknown"
    stage: str = ""
    message: str = ""
    updated_at: str = ""
    report_html: str = ""
    monitor_html: str = ""


class RunFile(BaseModel):
    name: str
    path: str
    kind: str
    size: int


class ProcessStartResponse(BaseModel):
    id: str
    path: str
    pid: int | None = None
    command: list[str]

