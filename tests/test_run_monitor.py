# -*- coding: utf-8 -*-

import json

from litsurveygrp.run_monitor import RunMonitor, RunMonitorViewer, run_from_args


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


def test_run_monitor_viewer_creates_idle_monitor_and_prints_paths(tmp_path):
    printed = []
    opened = []
    viewer = RunMonitorViewer(
        tmp_path / "results",
        open_browser=True,
        once=True,
        browser_open_func=opened.append,
        print_func=printed.append,
    )

    assert viewer.run() == 0

    assert (tmp_path / "results" / "run_status.json").exists()
    assert (tmp_path / "results" / "run_monitor.html").exists()
    assert opened and opened[0].startswith("file:")
    assert any("Monitor HTML:" in line for line in printed)
    assert any("idle" in line for line in printed)


def test_run_monitor_cli_adapter_runs(monkeypatch, tmp_path):
    class Args:
        results_dir = str(tmp_path / "results")
        open = True
        watch = False
        once = True
        interval = 2

    captured = {}

    def fake_run(self):
        captured["results_dir"] = self.results_dir
        captured["open_browser"] = self.open_browser
        captured["once"] = self.once
        captured["interval"] = self.interval
        return 0

    monkeypatch.setattr(RunMonitorViewer, "run", fake_run)

    assert run_from_args(Args()) == 0
    assert captured["results_dir"].name == "results"
    assert captured["open_browser"] is True
    assert captured["once"] is True
    assert captured["interval"] == 2
