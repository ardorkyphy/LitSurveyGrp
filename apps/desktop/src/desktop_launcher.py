from __future__ import annotations

import socket
import sys
import threading
import time
import traceback
from datetime import datetime
from os import environ
from pathlib import Path

import uvicorn
import webview

from litsurveygrp.webapi.app import create_app


def log_path() -> Path:
    base = Path(environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "LitSurveyGrp" / "logs" / "desktop.log"


def log(message: str) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return repo_root()


def web_dist_dir() -> Path:
    return resource_root() / "apps" / "web" / "dist"


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no local port available")


def start_api(root: Path, port: int) -> uvicorn.Server:
    config = uvicorn.Config(
        create_app(root, web_dist=web_dist_dir()),
        host="127.0.0.1",
        port=port,
        log_level="info",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for_port(port, timeout_seconds=15)
    return server


def wait_for_port(port: int, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for API port {port}")


def main() -> None:
    log("startup begin")
    log(f"sys.executable={sys.executable}")
    log(f"sys.frozen={getattr(sys, 'frozen', False)}")
    log(f"sys._MEIPASS={getattr(sys, '_MEIPASS', '')}")
    root = repo_root()
    dist = web_dist_dir()
    index = dist / "index.html"
    log(f"repo_root={root}")
    log(f"resource_root={resource_root()}")
    log(f"web_dist={dist} exists={dist.exists()}")
    log(f"index_html={index} exists={index.exists()}")
    log(f"assets_dir={dist / 'assets'} exists={(dist / 'assets').exists()}")
    if not dist.exists():
        raise RuntimeError(f"Missing web build output: {dist}")
    if not index.exists():
        raise RuntimeError(f"Missing web index: {index}")
    port = find_free_port(8000)
    app_url = f"http://127.0.0.1:{port}/?apiBase=http%3A%2F%2F127.0.0.1%3A{port}"
    log(f"selected_port={port}")
    server = start_api(root, port)
    log(f"api_started url=http://127.0.0.1:{port}")
    log(f"window_url={app_url}")
    webview.create_window(
        "LitSurveyGrp",
        app_url,
        width=1440,
        height=960,
        min_size=(1200, 800),
    )
    webview.start(gui="edgechromium", debug=True)
    log("webview stopped")
    server.should_exit = True
    log("startup end")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("fatal exception")
        log(traceback.format_exc())
        raise
