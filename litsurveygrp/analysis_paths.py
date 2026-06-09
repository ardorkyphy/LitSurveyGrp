# -*- coding: utf-8 -*-
"""Canonical directory naming for agent analysis artifacts."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisLayout:
    papers_dir: Path
    results_dir: Path
    reports_dir: Path
    major_domain: str
    subdomain: str

    @property
    def data_domain_dir(self) -> Path:
        return self.results_dir / self.major_domain / self.subdomain

    @property
    def papers_domain_dir(self) -> Path:
        return self.papers_dir / self.major_domain / self.subdomain

    @property
    def analysis_domain_dir(self) -> Path:
        return self.results_dir / self.major_domain / self.subdomain

    @property
    def report_domain_dir(self) -> Path:
        return self.reports_dir / self.major_domain / self.subdomain

    @property
    def report_data_dir(self) -> Path:
        return self.reports_dir / self.major_domain / "data"


def survey_roots(root: Path) -> dict[str, Path]:
    root = Path(root)
    return {
        "papers": root / "papers",
        "results": root / "results",
        "reports": root / "reports",
    }


def report_data_dir(reports_dir: Path, major_domain: str) -> Path:
    return Path(reports_dir) / major_domain / "data"


def major_domain_name(value: str) -> str:
    text = (value or "").strip()
    lowered = text.casefold()
    if "neuroscience" in lowered:
        return "Neuroscience"
    if "aging" in lowered or "ageing" in lowered:
        return "aging"
    return safe_path_name(text or "analysis")


def subdomain_name(value: str, fallback: str = "general") -> str:
    text = (value or "").strip()
    if not text:
        return safe_path_name(fallback)
    part = [item.strip() for item in text.split(">") if item.strip()]
    return safe_path_name(part[-1] if part else text)


def article_major_domain(article, fallback: str = "analysis") -> str:
    value = getattr(article, "classification_source_label", "") or getattr(article, "subdomain", "")
    text = (value or "").strip()
    parts = [item.strip() for item in text.split(">") if item.strip()]
    if parts:
        return safe_path_name(parts[0])
    return major_domain_name(fallback)


def article_subdomain(article, fallback: str = "general") -> str:
    value = getattr(article, "classification_source_label", "") or getattr(article, "subdomain", "")
    return subdomain_name(value, fallback)


def safe_path_name(value: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", (value or "").strip())
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._-")
    return text or "untitled"
