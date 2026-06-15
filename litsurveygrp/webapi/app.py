from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from litsurveygrp.webapi.runs import RunStore, SurveyRunner, journal_schema, stage_schema
from litsurveygrp.webapi.schemas import RunCreateRequest


def create_app(workspace: Path | None = None, web_dist: Path | None = None) -> FastAPI:
    root = Path(workspace or Path.cwd())
    store = RunStore(root)
    runner = SurveyRunner(root)
    app = FastAPI(title="LitSurveyGrp Local Console")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/stages")
    def get_stages():
        return stage_schema()

    @app.get("/api/journals")
    def get_journals():
        return journal_schema()

    @app.get("/api/runs")
    def list_runs():
        return store.list_runs()

    @app.post("/api/runs")
    def create_run(request: RunCreateRequest):
        try:
            return runner.start(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        path = store.resolve_run(run_id)
        summary = store.summary_for(path)
        if summary is None:
            raise HTTPException(status_code=404, detail="run not found")
        return summary

    @app.get("/api/runs/{run_id}/status")
    def get_status(run_id: str):
        path = store.resolve_run(run_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="run not found")
        return store.read_status(path)

    @app.get("/api/runs/{run_id}/files")
    def get_files(run_id: str):
        path = store.resolve_run(run_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="run not found")
        return store.files_for(path)

    @app.get("/api/runs/{run_id}/manifest")
    def get_manifest(run_id: str, name: str = "classified_manifest.json"):
        path = store.resolve_run(run_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="run not found")
        return store.manifest_for(path, name=name)

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str):
        try:
            store.delete_run(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"deleted": run_id}

    if web_dist is not None:
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
