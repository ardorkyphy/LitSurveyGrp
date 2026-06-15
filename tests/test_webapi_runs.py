import json
import subprocess
import sys

from fastapi.testclient import TestClient

from litsurveygrp.webapi.app import create_app
from litsurveygrp.webapi.runs import RunStore, SurveyRunner, stage_schema
from litsurveygrp.webapi.schemas import RunCreateRequest, StageOption


def test_stage_schema_exposes_core_stage_controls():
    stages = stage_schema()
    keys = {stage.key for stage in stages}

    assert "discovery" in keys
    assert "pdf_download" in keys
    assert "final_report" in keys
    assert all(stage.modes for stage in stages)


def test_survey_runner_builds_stage_control_command(tmp_path):
    runner = SurveyRunner(tmp_path)
    request = RunCreateRequest(
        out="run",
        journal=["nature-aging"],
        keyword=["wearable"],
        preset="full",
        limit=10,
        stage_control={
            "stats": StageOption(key="stats", label="Stats", enabled=False),
            "pdf_download": StageOption(key="pdf_download", label="PDF", enabled=True, mode="top-ranked"),
        },
    )

    command = runner.build_command(request)

    assert command[:4] == [command[0], "-m", "litsurveygrp", "survey"]
    assert "--journal" in command
    assert "nature-aging" in command
    assert "--keyword" in command
    assert "wearable" in command
    assert command[command.index("--skip-stage") + 1] == "stats"
    assert "pdf_download=top-ranked" in command


def test_run_store_reads_status_files(tmp_path):
    run = tmp_path / "run_a"
    data = run / "reports" / "aging" / "data"
    data.mkdir(parents=True)
    (data / "run_status.json").write_text(json.dumps({
        "status": "completed",
        "stage": "final_report",
        "message": "done",
        "updated_at": "2026-01-01T00:00:00",
    }), encoding="utf-8")
    (data / "classified_manifest.json").write_text(json.dumps([{"title": "Paper"}]), encoding="utf-8")

    store = RunStore(tmp_path)
    runs = store.list_runs()

    assert runs[0].id == "run_a"
    assert runs[0].status == "completed"
    assert store.manifest_for(run) == [{"title": "Paper"}]


def test_webapi_lists_stages_and_runs(tmp_path):
    run = tmp_path / "run_a"
    data = run / "reports" / "aging" / "data"
    data.mkdir(parents=True)
    (data / "run_status.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    app = create_app(tmp_path)
    client = TestClient(app)

    assert client.get("/api/stages").status_code == 200
    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "run_a"


def test_webapi_import_does_not_load_pipeline():
    script = (
        "import sys; "
        "import litsurveygrp.webapi.runs; "
        "assert 'litsurveygrp.pipeline' not in sys.modules"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
