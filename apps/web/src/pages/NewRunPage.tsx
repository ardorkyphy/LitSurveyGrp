import type { JournalOption, StageOption } from "../features/runs/types";
import { RunLauncherForm } from "../features/launcher/RunLauncherForm";

type NewRunPageProps = {
  stages: StageOption[];
  journals: JournalOption[];
  onCreated: (runId: string) => void;
};

export function NewRunPage({ stages, journals, onCreated }: NewRunPageProps) {
  return <RunLauncherForm stages={stages} journals={journals} onCreated={onCreated} />;
}

