# -*- coding: utf-8 -*-
"""Lightweight run-status monitor for long literature-survey workflows."""

import html
import json
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any


class RunMonitor:
    """Write a refreshable HTML page and JSON status for a running workflow."""

    def __init__(
        self,
        out_dir: Path,
        enabled: bool = True,
        refresh_seconds: int = 5,
        status_name: str = "run_status.json",
        html_name: str = "run_monitor.html",
    ):
        self.out_dir = Path(out_dir)
        self.enabled = enabled
        self.refresh_seconds = max(1, int(refresh_seconds or 5))
        self.status_path = self.out_dir / status_name
        self.html_path = self.out_dir / html_name
        self.state = {
            "run_name": "",
            "status": "created",
            "stage": "",
            "message": "",
            "started_at": "",
            "updated_at": "",
            "finished_at": "",
            "processed": 0,
            "total": None,
            "current_item": "",
            "metrics": {},
            "events": [],
        }

    def start(self, run_name: str, message: str = "", metrics: dict | None = None) -> None:
        now = self.now()
        self.state.update({
            "run_name": run_name,
            "status": "running",
            "stage": "starting",
            "message": message or "Run started",
            "started_at": self.state.get("started_at") or now,
            "updated_at": now,
            "finished_at": "",
            "metrics": self.safe(metrics or {}),
        })
        self.add_event("started", message or run_name)
        self.write()

    def update(
        self,
        stage: str | None = None,
        message: str | None = None,
        processed: int | None = None,
        total: int | None = None,
        current_item: str | None = None,
        metrics: dict | None = None,
        status: str = "running",
    ) -> None:
        self.state["status"] = status
        if stage is not None:
            self.state["stage"] = stage
        if message is not None:
            self.state["message"] = message
        if processed is not None:
            self.state["processed"] = int(processed)
        if total is not None:
            self.state["total"] = int(total)
        if current_item is not None:
            self.state["current_item"] = current_item
        if metrics:
            current = dict(self.state.get("metrics") or {})
            current.update(self.safe(metrics))
            self.state["metrics"] = current
        self.state["updated_at"] = self.now()
        self.write()

    def finish(self, status: str = "completed", message: str = "") -> None:
        now = self.now()
        self.state["status"] = status
        self.state["message"] = message or status
        self.state["updated_at"] = now
        self.state["finished_at"] = now
        self.add_event(status, message or status)
        self.write()

    def add_event(self, event_type: str, message: str) -> None:
        events = list(self.state.get("events") or [])
        events.append({
            "time": self.now(),
            "type": event_type,
            "message": message,
        })
        self.state["events"] = events[-100:]

    def write(self) -> None:
        if not self.enabled:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        with open(self.status_path, "w", encoding="utf-8") as handle:
            json.dump(self.safe(self.state), handle, ensure_ascii=False, indent=2)
        with open(self.html_path, "w", encoding="utf-8") as handle:
            handle.write(self.render_html())

    def render_html(self) -> str:
        state = self.safe(self.state)
        title = state.get("run_name") or "LitSurveyGrp run"
        status = state.get("status") or ""
        stage = state.get("stage") or ""
        processed = state.get("processed") or 0
        total = state.get("total")
        percent = ""
        bar_width = "0"
        if total:
            value = min(100.0, max(0.0, processed / max(1, total) * 100))
            percent = f"{value:.1f}%"
            bar_width = f"{value:.1f}%"
        metrics = state.get("metrics") or {}
        metric_rows = "\n".join(
            f"<tr><th>{self.escape(key)}</th><td>{self.escape(value)}</td></tr>"
            for key, value in metrics.items()
        )
        events = list(state.get("events") or [])[-20:]
        event_rows = "\n".join(
            "<tr>"
            f"<td>{self.escape(event.get('time', ''))}</td>"
            f"<td>{self.escape(event.get('type', ''))}</td>"
            f"<td>{self.escape(event.get('message', ''))}</td>"
            "</tr>"
            for event in reversed(events)
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{self.refresh_seconds}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{self.escape(title)} Monitor</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1f2933; background: #f7f9fb; }}
    main {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin: 0 0 16px; }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 4px; background: #e8eef7; font-weight: 600; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 16px 0; }}
    .panel {{ background: white; border: 1px solid #d9e2ec; border-radius: 6px; padding: 14px; }}
    .label {{ color: #52606d; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 18px; margin-top: 6px; overflow-wrap: anywhere; }}
    .progress {{ height: 14px; border-radius: 4px; background: #d9e2ec; overflow: hidden; }}
    .bar {{ height: 100%; width: {bar_width}; background: #2f80ed; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d9e2ec; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #eef2f6; text-align: left; vertical-align: top; }}
    th {{ color: #52606d; width: 220px; }}
    .muted {{ color: #697586; }}
  </style>
</head>
<body>
<main>
  <h1>{self.escape(title)}</h1>
  <p><span class="status">{self.escape(status)}</span> <span class="muted">Auto-refresh every {self.refresh_seconds}s</span></p>
  <section class="grid">
    <div class="panel"><div class="label">Stage</div><div class="value">{self.escape(stage)}</div></div>
    <div class="panel"><div class="label">Processed</div><div class="value">{self.escape(processed)}{self.escape('/' + str(total) if total else '')} {self.escape(percent)}</div></div>
    <div class="panel"><div class="label">Updated</div><div class="value">{self.escape(state.get('updated_at', ''))}</div></div>
    <div class="panel"><div class="label">Current Item</div><div class="value">{self.escape(state.get('current_item', ''))}</div></div>
  </section>
  <div class="progress"><div class="bar"></div></div>
  <section class="panel">
    <div class="label">Message</div>
    <div class="value">{self.escape(state.get('message', ''))}</div>
  </section>
  <h2>Metrics</h2>
  <table>{metric_rows or '<tr><td class="muted">No metrics yet</td></tr>'}</table>
  <h2>Recent Events</h2>
  <table>
    <tr><th>Time</th><th>Type</th><th>Message</th></tr>
    {event_rows or '<tr><td class="muted" colspan="3">No events yet</td></tr>'}
  </table>
</main>
</body>
</html>
"""

    def now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def safe(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self.safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self.safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def escape(self, value: Any) -> str:
        return html.escape(str(value if value is not None else ""))


class RunMonitorViewer:
    """CLI helper for opening or watching a monitor output directory."""

    def __init__(
        self,
        results_dir: Path,
        open_browser: bool = False,
        watch: bool = False,
        interval: int = 5,
        once: bool = False,
        browser_open_func=None,
        sleep_func=None,
        print_func=None,
    ):
        self.results_dir = Path(results_dir)
        self.open_browser = open_browser
        self.watch = watch
        self.interval = max(1, int(interval or 5))
        self.once = once
        self.browser_open_func = browser_open_func or webbrowser.open
        self.sleep_func = sleep_func or time.sleep
        self.print_func = print_func or print
        self.monitor = RunMonitor(self.results_dir)

    @property
    def status_path(self) -> Path:
        return self.monitor.status_path

    @property
    def html_path(self) -> Path:
        return self.monitor.html_path

    def run(self) -> int:
        self.ensure_monitor_files()
        self.print_func(f"Monitor HTML: {self.html_path.resolve()}")
        self.print_func(f"Monitor JSON: {self.status_path.resolve()}")
        if self.open_browser:
            self.browser_open_func(self.html_path.resolve().as_uri())
        if self.watch or self.once:
            self.watch_status()
        return 0

    def ensure_monitor_files(self) -> None:
        if not self.status_path.exists():
            self.monitor.start("LitSurveyGrp monitor", "Waiting for a run to write status")
            self.monitor.finish("idle", "No active run status found yet")
        elif not self.html_path.exists():
            self.monitor.state = self.load_status()
            self.monitor.write()

    def watch_status(self) -> None:
        while True:
            state = self.load_status()
            self.print_func(self.format_status(state))
            if self.once:
                return
            self.sleep_func(self.interval)

    def load_status(self) -> dict:
        if not self.status_path.exists():
            return {}
        with open(self.status_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def format_status(self, state: dict) -> str:
        if not state:
            return "No run status found."
        total = state.get("total")
        processed = state.get("processed", 0)
        progress = f"{processed}/{total}" if total else str(processed)
        return (
            f"[{state.get('updated_at', '')}] "
            f"{state.get('status', '')} "
            f"{state.get('stage', '')} "
            f"processed={progress} "
            f"current={state.get('current_item', '')} "
            f"message={state.get('message', '')}"
        )


def run_from_args(args) -> int:
    viewer = RunMonitorViewer(
        Path(getattr(args, "results_dir", "results")),
        open_browser=getattr(args, "open", False),
        watch=getattr(args, "watch", False),
        interval=getattr(args, "interval", 5),
        once=getattr(args, "once", False),
    )
    return viewer.run()
