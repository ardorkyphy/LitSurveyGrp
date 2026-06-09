# -*- coding: utf-8 -*-
"""Safe cleanup for generated experiment outputs."""

import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CLEAN_TARGETS = ["papers", "results", "reports"]


@dataclass
class CleanupResult:
    """Result for one cleanup target."""

    path: Path
    status: str

    def to_dict(self) -> dict:
        return {"path": str(self.path), "status": self.status}


class GeneratedOutputCleaner:
    """Remove generated output directories with strict workspace safety checks."""

    def __init__(self, workspace: Path | None = None, targets: list[str] | None = None, dry_run: bool = False):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.targets = targets or list(DEFAULT_CLEAN_TARGETS)
        self.dry_run = dry_run

    def run(self) -> list[CleanupResult]:
        results = []
        for target in self.targets:
            path = self.resolve_target(target)
            if not path.exists():
                results.append(CleanupResult(path, "missing"))
                continue
            if self.dry_run:
                results.append(CleanupResult(path, "would_delete"))
                continue
            shutil.rmtree(path)
            results.append(CleanupResult(path, "deleted"))
        return results

    def resolve_target(self, target: str) -> Path:
        raw = Path(target)
        if raw.is_absolute():
            path = raw.resolve()
        else:
            path = (self.workspace / raw).resolve()
        self.validate_target(path)
        return path

    def validate_target(self, path: Path) -> None:
        if path == self.workspace:
            raise ValueError(f"refusing to clean workspace root: {path}")
        if path == Path(path.anchor):
            raise ValueError(f"refusing to clean filesystem root: {path}")
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError(f"refusing to clean path outside workspace: {path}") from exc


def run_from_args(args) -> int:
    cleaner = GeneratedOutputCleaner(
        workspace=Path.cwd(),
        targets=getattr(args, "target", None) or list(DEFAULT_CLEAN_TARGETS),
        dry_run=getattr(args, "dry_run", False),
    )
    for result in cleaner.run():
        print(f"{result.status}\t{result.path}")
    return 0
