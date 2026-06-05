# -*- coding: utf-8 -*-

import json

from litsurveygrp.run_monitor import RunMonitor


def test_run_monitor_writes_json_and_refreshing_html(tmp_path):
    monitor = RunMonitor(tmp_path / "results", refresh_seconds=3)

    monitor.start("Survey", "Starting")
    monitor.update(
        stage="download",
        message="Processing records",
        processed=5,
        total=10,
        current_item="中文论文",
        metrics={"provider": "Nature crawler"},
    )
    monitor.finish("completed", "Done")

    status = json.loads((tmp_path / "results" / "run_status.json").read_text(encoding="utf-8"))
    html = (tmp_path / "results" / "run_monitor.html").read_text(encoding="utf-8")

    assert status["run_name"] == "Survey"
    assert status["status"] == "completed"
    assert status["stage"] == "download"
    assert status["processed"] == 5
    assert status["total"] == 10
    assert status["metrics"]["provider"] == "Nature crawler"
    assert "中文论文" in html
    assert 'http-equiv="refresh" content="3"' in html


def test_run_monitor_can_be_disabled(tmp_path):
    monitor = RunMonitor(tmp_path / "results", enabled=False)

    monitor.start("Survey")
    monitor.update(stage="download", processed=1)

    assert not (tmp_path / "results" / "run_status.json").exists()
    assert not (tmp_path / "results" / "run_monitor.html").exists()
