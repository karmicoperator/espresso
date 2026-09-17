import type { Explainer, ExplainerSummary } from "./types";

/** The backend origin. CORS is enabled server-side, so no proxy sits in between. */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
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
