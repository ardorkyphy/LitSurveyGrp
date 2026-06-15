import { useMemo, useState } from "react";
import { runsApi } from "../features/runs/api";
import { RunFilesPanel } from "../features/runs/RunFilesPanel";
import { RunList } from "../features/runs/RunList";
import { RunManifestTable } from "../features/runs/RunManifestTable";
import { RunStatusPanel } from "../features/monitor/RunStatusPanel";
import { useAsyncData } from "../features/runs/hooks";

type RunsPageProps = {
  selectedId: string;
  onSelect: (id: string) => void;
};

export function RunsPage({ selectedId, onSelect }: RunsPageProps) {
  const runs = useAsyncData(() => runsApi.list(), []);
  const status = useAsyncData(() => (selectedId ? runsApi.status(selectedId) : Promise.resolve(null)), [selectedId]);
  const files = useAsyncData(() => (selectedId ? runsApi.files(selectedId) : Promise.resolve([])), [selectedId]);
  const manifest = useAsyncData(() => (selectedId ? runsApi.manifest(selectedId) : Promise.resolve([])), [selectedId]);
  const [error, setError] = useState("");

  async function refresh() {
    setError("");
    await runs.setData(await runsApi.list());
  }

  async function deleteRun(id: string) {
    await runsApi.delete(id);
    await refresh();
  }

  const selected = useMemo(() => runs.data?.find((item) => item.id === selectedId) || null, [runs.data, selectedId]);

  return (
    <div className="workspace">
      <RunList
        runs={runs.data || []}
        selectedId={selectedId}
        onSelect={onSelect}
        onRefresh={refresh}
        onDelete={deleteRun}
      />
      <div className="stack">
        {error && <div className="error">{error}</div>}
        <RunStatusPanel status={status.data} />
        <RunFilesPanel files={files.data || []} />
        <RunManifestTable rows={manifest.data || []} />
        {selected && <div className="panel muted">{selected.path}</div>}
      </div>
    </div>
  );
}

