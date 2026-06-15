import { RefreshCw, Trash2 } from "lucide-react";
import { Button } from "../../components/ui/Button";
import type { RunSummary } from "./types";

type RunListProps = {
  runs: RunSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  onDelete: (id: string) => void;
};

export function RunList({ runs, selectedId, onSelect, onRefresh, onDelete }: RunListProps) {
  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <h1>Runs</h1>
          <p>{runs.length} local run directories</p>
        </div>
        <Button onClick={onRefresh}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </div>
      <div className="run-list">
        {runs.map((run) => (
          <button key={run.id} className={run.id === selectedId ? "run-item active" : "run-item"} onClick={() => onSelect(run.id)}>
            <div>
              <strong>{run.id}</strong>
              <span>{run.message || run.stage || run.status}</span>
            </div>
            <span className={`status ${run.status}`}>{run.status}</span>
            <Trash2
              size={16}
              onClick={(event) => {
                event.stopPropagation();
                onDelete(run.id);
              }}
            />
          </button>
        ))}
      </div>
    </div>
  );
}

