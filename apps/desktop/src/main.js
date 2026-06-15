import { app, BrowserWindow, dialog } from "electron";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
let backendProcess = null;
let backendReady = false;

function rootDir() {
  return path.resolve(__dirname, "..", "..", "..");
}

function webDistDir() {
  return path.resolve(rootDir(), "apps", "web", "dist");
}

function pythonExecutable() {
  return process.env.PYTHON || "python";
}

async function ensureBackend() {
  if (backendProcess) {
    return;
  }
  backendProcess = spawn(
    pythonExecutable(),
    ["-m", "uvicorn", "litsurveygrp.webapi.app:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: rootDir(), windowsHide: true, stdio: "ignore" }
  );
  backendProcess.on("exit", () => {
    backendProcess = null;
    backendReady = false;
  });
  await waitForHttp("http://127.0.0.1:8000/api/stages", 15000);
  backendReady = true;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1200,
    minHeight: 800,
    title: "LitSurveyGrp",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  const dist = webDistDir();
  if (!existsSync(dist)) {
    dialog.showErrorBox(
      "LitSurveyGrp",
      `Missing web build output at ${dist}. Build apps/web first with npm run build.`
    );
    app.quit();
    return null;
  }
  win.loadFile(path.join(dist, "index.html"));
  return win;
}

async function waitForHttp(url, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

app.whenReady().then(async () => {
  try {
    await ensureBackend();
    createWindow();
  } catch (error) {
    dialog.showErrorBox("LitSurveyGrp startup failed", String(error?.message || error));
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
