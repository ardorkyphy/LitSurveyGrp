export type StageOption = {
  key: string;
  label: string;
  enabled: boolean;
  mode: string;
  modes: string[];
};

export type RunSummary = {
  id: string;
  path: string;
  status: string;
  stage: string;
  message: string;
  updated_at: string;
  report_html: string;
  monitor_html: string;
};

export type RunFile = {
  name: string;
  path: string;
  kind: string;
  size: number;
};

export type JournalOption = {
  key: string;
  name: string;
  provider: string;
  group: string;
  issn: string;
};

export type RunCreateRequest = {
  out: string;
  query: string;
  journal: string[];
  keyword: string[];
  preset: string;
  limit?: number;
  per_journal_limit?: number;
  pdfs?: number;
  title: string;
  stage_control: Record<string, StageOption>;
};

export type RunStatus = {
  run_name?: string;
  status?: string;
  stage?: string;
  message?: string;
  updated_at?: string;
  processed?: number;
  total?: number;
  current_item?: string;
  metrics?: Record<string, unknown>;
  events?: Array<{ time: string; type: string; message: string }>;
};

