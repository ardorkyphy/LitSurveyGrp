# -*- coding: utf-8 -*-
"""Manifest and report writers shared by workflow services."""

import csv
import json
from pathlib import Path

from litsurveygrp.paper_models import ArticleRecord


class ArticleManifestWriter:
    """Write article records to the project JSON manifest format."""

    def __init__(self, output_dir: Path, filename: str):
        self.output_dir = Path(output_dir)
        self.filename = filename

    def write(self, articles: list[ArticleRecord]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / self.filename
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([article.to_manifest_dict() for article in articles], handle, ensure_ascii=False, indent=2)
        return path


class DownloadReportWriter:
    """Write a compact CSV report for download attempts."""

    FIELDS = [
        "journal",
        "title",
        "doi",
        "pdf_url",
        "local_pdf_path",
        "download_status",
        "pdf_status",
        "error",
    ]

    def __init__(self, output_dir: Path, filename: str):
        self.output_dir = Path(output_dir)
        self.filename = filename

    def write(self, articles: list[ArticleRecord]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / self.filename
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDS)
            writer.writeheader()
            for article in articles:
                row = article.to_manifest_dict()
                writer.writerow({field: row.get(field, "") for field in self.FIELDS})
        return path

