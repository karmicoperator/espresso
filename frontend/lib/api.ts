import type { Explainer, ExplainerSummary, Health, Job, SettingsView } from "./types";

/**
 * Same origin: app/api/[...path]/route.ts forwards every /api request to the API, so the
 * page never needs to know which port the API is on.
 */
export const API_BASE = "";

/**
 * A failure the page can show. `kind` is set for the cases the reader can do something
 * about, and `url` says where; "not_in_pmc" is the one that offers the PDF route.
 */
export class ApiError extends Error {
  kind: string;
  url: string;
  constructor(message: string, kind = "", url = "") {
    super(message);
    this.kind = kind;
    this.url = url;
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const d = body.detail;
    if (d && typeof d === "object") throw new ApiError(d.message, d.kind, d.url);
    throw new ApiError(typeof d === "string" ? d : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then(json<Health>),

  settings: () => fetch(`${API_BASE}/api/settings`, { cache: "no-store" }).then(json<SettingsView>),

  /** Saves one provider's settings to backend/.env and makes it the active one. */
  saveSettings: (body: {
    provider: string;
    model: string;
    api_key: string;
    base_url?: string | null;
    endpoint?: string | null;
  }) =>
    fetch(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<SettingsView>),

  /** One tiny call through the active provider. */
  testSettings: () =>
    fetch(`${API_BASE}/api/settings/test`, { method: "POST" }).then(json<{ ok: boolean; message: string }>),

  /** Removes a built paper with its text, PDF and figures. This machine only. */
  remove: (paperId: string) =>
    fetch(`${API_BASE}/api/explainer/${encodeURIComponent(paperId)}`, { method: "DELETE" }).then(json<{ removed: string }>),
  list: () =>
    fetch(`${API_BASE}/api/explainers`, { cache: "no-store" }).then(json<ExplainerSummary[]>),

  get: (paperId: string) =>
    fetch(`${API_BASE}/api/explainer/${encodeURIComponent(paperId)}`, { cache: "no-store" }).then(
      json<Explainer>,
    ),

  /** Start a build. Returns at once with a job to poll; the build runs on the API. */
  startBuild: (input: string, forceRefresh = false) =>
    fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, force_refresh: forceRefresh }),
    }).then(json<Job>),

  /**
   * Build from a PDF the reader downloaded themselves.
   *
   * A quarter of PubMed's free full text was never deposited in PubMed Central, and the
   * publishers hosting it refuse automated downloads. They do not refuse people, so this
   * is the route for everything the PMC path cannot reach.
   */
  startPdfBuild: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return fetch(`${API_BASE}/api/jobs/pdf`, { method: "POST", body }).then(json<Job>);
  },

  jobs: () => fetch(`${API_BASE}/api/jobs`, { cache: "no-store" }).then(json<Job[]>),
};
