export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function apiUrl(path: string): string {
  const params = new URLSearchParams(globalThis.location?.search || "");
  const base = (globalThis as typeof globalThis & { __LITSURVEY_API_BASE__?: string }).__LITSURVEY_API_BASE__ || params.get("apiBase") || "";
  if (base) {
    return `${base}${path}`;
  }
  if (globalThis.location?.protocol === "file:") {
    return `http://127.0.0.1:8000${path}`;
  }
  return path;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}
