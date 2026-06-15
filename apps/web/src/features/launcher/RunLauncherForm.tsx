import { useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { runsApi } from "../runs/api";
import type { JournalOption, RunCreateRequest, StageOption } from "../runs/types";
import { StageControlEditor } from "./StageControlEditor";

type RunLauncherFormProps = {
  stages: StageOption[];
  journals: JournalOption[];
  onCreated: (runId: string) => void;
};

export function RunLauncherForm({ stages, journals, onCreated }: RunLauncherFormProps) {
  const [out, setOut] = useState("survey_run");
  const [query, setQuery] = useState("");
  const [journal, setJournal] = useState("nature-aging");
  const [keyword, setKeyword] = useState("");
  const [preset, setPreset] = useState("balanced");
  const [limit, setLimit] = useState("50");
  const [perJournalLimit, setPerJournalLimit] = useState("");
  const [pdfs, setPdfs] = useState("");
  const [title, setTitle] = useState("");
  const [stageState, setStageState] = useState(stages);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const journalOptions = useMemo(() => journals.length ? journals : [{ key: "nature-aging", name: "Nature Aging" } as JournalOption], [journals]);

  async function submit() {
    setSubmitting(true);
    setError("");
    const request: RunCreateRequest = {
      out,
      query,
      journal: journal ? [journal] : [],
      keyword: splitValues(keyword),
      preset,
      title,
      stage_control: Object.fromEntries(stageState.map((stage) => [stage.key, stage]))
    };
    assignNumber(request, "limit", limit);
    assignNumber(request, "per_journal_limit", perJournalLimit);
    assignNumber(request, "pdfs", pdfs);
    try {
      const response = await runsApi.create(request);
      onCreated(response.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <h1>New Survey Run</h1>
          <p>Configure a local LitSurveyGrp workflow.</p>
        </div>
        <Button onClick={submit} disabled={submitting}>
          <Play size={16} />
          {submitting ? "Starting" : "Start"}
        </Button>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="form-grid">
        <label>
          Output
          <input value={out} onChange={(event) => setOut(event.target.value)} />
        </label>
        <label>
          Query
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          Journal
          <select value={journal} onChange={(event) => setJournal(event.target.value)}>
            {journalOptions.map((item) => (
              <option key={item.key} value={item.key}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Keywords
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </label>
        <label>
          Preset
          <select value={preset} onChange={(event) => setPreset(event.target.value)}>
            <option value="fast">fast</option>
            <option value="balanced">balanced</option>
            <option value="full">full</option>
            <option value="metadata">metadata</option>
          </select>
        </label>
        <label>
          Limit
          <input value={limit} onChange={(event) => setLimit(event.target.value)} />
        </label>
        <label>
          Per Journal Limit
          <input value={perJournalLimit} onChange={(event) => setPerJournalLimit(event.target.value)} />
        </label>
        <label>
          PDFs
          <input value={pdfs} onChange={(event) => setPdfs(event.target.value)} />
        </label>
        <label className="wide">
          Report Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
      </div>
      <StageControlEditor stages={stageState} onChange={setStageState} />
    </div>
  );
}

function splitValues(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function assignNumber(target: RunCreateRequest, key: "limit" | "per_journal_limit" | "pdfs", value: string) {
  if (!value.trim()) return;
  const parsed = Number(value);
  if (Number.isFinite(parsed)) {
    target[key] = parsed;
  }
}

