import type { RunStatus } from "../runs/types";

type RunStatusPanelProps = {
  status: RunStatus | null;
};

export function RunStatusPanel({ status }: RunStatusPanelProps) {
  if (!status) {
    return <div className="panel muted">No run selected</div>;
  }
  const processed = status.processed ?? 0;
  const total = status.total ?? 0;
  const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <h1>{status.run_name || "Run Monitor"}</h1>
          <p>{status.message || "Waiting for status"}</p>
        </div>
        <span className={`status ${status.status || ""}`}>{status.status || "unknown"}</span>
      </div>
      <div className="metric-grid">
        <div><span>Stage</span><strong>{status.stage || "-"}</strong></div>
        <div><span>Processed</span><strong>{processed}{total ? ` / ${total}` : ""}</strong></div>
        <div><span>Updated</span><strong>{status.updated_at || "-"}</strong></div>
        <div><span>Current</span><strong>{status.current_item || "-"}</strong></div>
      </div>
      <div className="progress"><div style={{ width: `${percent}%` }} /></div>
      <div className="split">
        <div>
          <div className="section-title">Metrics</div>
          <table>
            <tbody>
              {Object.entries(status.metrics || {}).map(([key, value]) => (
                <tr key={key}><th>{key}</th><td>{String(value)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="section-title">Events</div>
          <div className="timeline">
            {(status.events || []).slice(-8).reverse().map((event, index) => (
              <div className="timeline-row" key={`${event.time}-${index}`}>
                <span>{event.time}</span>
                <strong>{event.type}</strong>
                <p>{event.message}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

