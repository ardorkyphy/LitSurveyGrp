import { apiDelete, apiGet, apiPost } from "../../lib/apiClient";
import type { JournalOption, RunCreateRequest, RunFile, RunStatus, RunSummary, StageOption } from "./types";

export const runsApi = {
  stages: () => apiGet<StageOption[]>("/api/stages"),
  journals: () => apiGet<JournalOption[]>("/api/journals"),
  list: () => apiGet<RunSummary[]>("/api/runs"),
  create: (request: RunCreateRequest) => apiPost<{ id: string; path: string; pid: number | null; command: string[] }>("/api/runs", request),
  status: (id: string) => apiGet<RunStatus>(`/api/runs/${encodeURIComponent(id)}/status`),
  files: (id: string) => apiGet<RunFile[]>(`/api/runs/${encodeURIComponent(id)}/files`),
  manifest: (id: string) => apiGet<Record<string, unknown>[]>(`/api/runs/${encodeURIComponent(id)}/manifest`),
  delete: (id: string) => apiDelete<{ deleted: string }>(`/api/runs/${encodeURIComponent(id)}`)
};

