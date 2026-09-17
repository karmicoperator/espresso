import type { Explainer, ExplainerSummary } from "./types";

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
  health: () => fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then(json<Record<string, unknown>>),

  list: () =>
    fetch(`${API_BASE}/api/explainers`, { cache: "no-store" }).then(json<ExplainerSummary[]>),

  get: (paperId: string) =>
    fetch(`${API_BASE}/api/explainer/${encodeURIComponent(paperId)}`, { cache: "no-store" }).then(
      json<Explainer>,
    ),

  /** Synchronous build. Three to five minutes on a trial paper; the caller shows progress. */
  build: (input: string, forceRefresh = false) =>
    fetch(`${API_BASE}/api/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, force_refresh: forceRefresh }),
    }).then(json<Explainer>),

  /**
   * Build from a PDF the reader downloaded themselves.
   *
   * A quarter of PubMed's free full text was never deposited in PubMed Central, and the
   * publishers hosting it refuse automated downloads. They do not refuse people, so this
   * is the route for everything the PMC path cannot reach.
   */
  buildFromPdf: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return fetch(`${API_BASE}/api/build/pdf`, { method: "POST", body }).then(json<Explainer>);
  },
};
