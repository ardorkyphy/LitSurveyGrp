import type { StageOption } from "../runs/types";

type StageControlEditorProps = {
  stages: StageOption[];
  onChange: (stages: StageOption[]) => void;
};

export function StageControlEditor({ stages, onChange }: StageControlEditorProps) {
  function updateStage(key: string, patch: Partial<StageOption>) {
    onChange(stages.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)));
  }

  return (
    <section>
      <div className="section-title">Stage Controls</div>
      <div className="stage-grid">
        {stages.map((stage) => (
          <div className="stage-row" key={stage.key}>
            <label className="stage-toggle">
              <input
                type="checkbox"
                checked={stage.enabled}
                onChange={(event) => updateStage(stage.key, { enabled: event.target.checked })}
              />
              <span>{stage.label}</span>
            </label>
            <select
              aria-label={`${stage.label} mode`}
              value={stage.mode}
              onChange={(event) => updateStage(stage.key, { mode: event.target.value })}
            >
              {stage.modes.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </section>
  );
}
