# -*- coding: utf-8 -*-

import pytest

from litsurveygrp.cleanup import GeneratedOutputCleaner, run_from_args


def test_cleaner_deletes_default_generated_dirs(tmp_path):
    papers = tmp_path / "papers"
    results = tmp_path / "results"
    papers.mkdir()
    results.mkdir()
    (papers / "paper.pdf").write_text("pdf", encoding="utf-8")

    outputs = GeneratedOutputCleaner(workspace=tmp_path).run()

    assert [item.status for item in outputs] == ["deleted", "deleted"]
    assert not papers.exists()
    assert not results.exists()


def test_cleaner_dry_run_does_not_delete(tmp_path):
    target = tmp_path / "results"
    target.mkdir()

    outputs = GeneratedOutputCleaner(workspace=tmp_path, targets=["results"], dry_run=True).run()

    assert outputs[0].status == "would_delete"
    assert target.exists()


def test_cleaner_reports_missing_targets(tmp_path):
    outputs = GeneratedOutputCleaner(workspace=tmp_path, targets=["papers"]).run()

    assert outputs[0].status == "missing"


def test_cleaner_refuses_unsafe_targets(tmp_path):
    cleaner = GeneratedOutputCleaner(workspace=tmp_path, targets=["."])

    with pytest.raises(ValueError):
        cleaner.run()

    with pytest.raises(ValueError):
        GeneratedOutputCleaner(workspace=tmp_path, targets=[str(tmp_path.parent)]).run()


def test_cleanup_cli_adapter_prints_results(capsys, tmp_path, monkeypatch):
    class Args:
        target = ["results"]
        dry_run = True

    (tmp_path / "results").mkdir()
    monkeypatch.chdir(tmp_path)

    assert run_from_args(Args()) == 0
    output = capsys.readouterr().out

    assert "would_delete" in output
    assert "results" in output

