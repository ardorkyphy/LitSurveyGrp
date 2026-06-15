import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "../components/layout/AppShell";
import { runsApi } from "../features/runs/api";
import type { JournalOption, StageOption } from "../features/runs/types";
import { NewRunPage } from "../pages/NewRunPage";
import { RunsPage } from "../pages/RunsPage";
import "../styles/globals.css";

function App() {
  const [view, setView] = useState("runs");
  const [selectedId, setSelectedId] = useState("");
  const [stages, setStages] = useState<StageOption[]>([]);
  const [journals, setJournals] = useState<JournalOption[]>([]);

  useEffect(() => {
    runsApi.stages().then(setStages).catch(() => setStages([]));
    runsApi.journals().then(setJournals).catch(() => setJournals([]));
  }, []);

  return (
    <AppShell view={view} onViewChange={setView}>
      {view === "runs" && <RunsPage selectedId={selectedId} onSelect={setSelectedId} />}
      {view === "new" && <NewRunPage stages={stages} journals={journals} onCreated={(runId) => { setSelectedId(runId); setView("runs"); }} />}
      {view === "files" && <RunsPage selectedId={selectedId} onSelect={setSelectedId} />}
    </AppShell>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

