// espresso, browser side. Two jobs the local app cannot do for itself:
//
//  1. One click from the paper's page. The tab's URL (PubMed, PMC, a DOI page) goes to
//     the local API, which builds the explainer; the popup follows the job and opens it.
//  2. The PDF, fetched as the person. Publishers block programs, not people: the page a
//     reader is looking at usually links its PDF, and a fetch from that page carries the
//     reader's own session. That PDF is attached to the paper, so its sentences open in it.
//
// Talks only to localhost, the espresso app on this machine; the extension itself sends
// nothing anywhere else. The app then sends the paper's text to the model the person picked.

const DEFAULT_API = "http://localhost:8000";
const DEFAULT_WEB = "http://localhost:3000";

async function settings() {
  const s = await chrome.storage.local.get({ api: DEFAULT_API, web: DEFAULT_WEB });
  return { api: s.api.replace(/\/$/, ""), web: s.web.replace(/\/$/, "") };
}

/** What the current tab is: a PubMed/PMC/DOI page, a PDF, or something else. */
function classify(url) {
  const u = new URL(url);
  const host = u.hostname;
  const pmc = url.match(/PMC\d{4,}/);
  if (u.pathname.toLowerCase().endsWith(".pdf")) return { kind: "pdf", url };
  if (host.endsWith("ncbi.nlm.nih.gov") || host.endsWith("europepmc.org") || host === "doi.org" || u.pathname.includes("/10.")) {
    return { kind: "paper", url, pmcid: pmc ? pmc[0] : null };
  }
  if (pmc) return { kind: "paper", url, pmcid: pmc[0] };
  return { kind: "other", url };
}

/** Runs in the page: find the PDF the page offers and fetch it with the page's own session. */
async function pdfFromPage() {
  const candidates = [];
  const meta = document.querySelector('meta[name="citation_pdf_url"]');
  if (meta?.content) candidates.push(meta.content);
  for (const a of document.querySelectorAll("a[href]")) {
    const h = a.href;
    if (/\.pdf(\?|$)/i.test(h) || /\/pdf\/?(\?|$)/i.test(h)) candidates.push(h);
  }
  for (const href of [...new Set(candidates)].slice(0, 4)) {
    try {
      const r = await fetch(href, { credentials: "include" });
      if (!r.ok) continue;
      const buf = await r.arrayBuffer();
      const head = new Uint8Array(buf.slice(0, 5));
      if (String.fromCharCode(...head) !== "%PDF-") continue;
      // Bytes cross to the worker as base64; a paper is a few MB, fine.
      let bin = "";
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      return { href, base64: btoa(bin) };
    } catch {
      /* next candidate */
    }
  }
  return null;
}

function bytesOf(base64) {
  const bin = atob(base64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function apiOk(api) {
  try {
    const r = await fetch(`${api}/api/health`);
    return r.ok && (await r.json()).app === "espresso";
  } catch {
    return false;
  }
}

async function postPdf(api, path, bytes, name) {
  const body = new FormData();
  body.append("file", new Blob([bytes], { type: "application/pdf" }), name);
  const r = await fetch(`${api}${path}`, { method: "POST", body });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

async function waitForJob(api, id, onStep) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 3000));
    const j = await fetch(`${api}/api/jobs/${id}`).then((r) => r.json());
    onStep?.(j);
    if (j.status === "done") return j;
    if (j.status === "failed" || j.status === "error") throw new Error(j.error?.message || "the build failed");
  }
}

/**
 * The whole flow for the active tab, reporting steps to the popup.
 *   paper page  → build from the URL; then, if the page offers a PDF, attach it.
 *   pdf tab     → build from the PDF bytes.
 */
async function run(tab, report) {
  const { api, web } = await settings();
  if (!(await apiOk(api))) throw new Error(`espresso is not running at ${api}. Start the app, then try again.`);
  const what = classify(tab.url);
  if (what.kind === "other") throw new Error("Open a PubMed, PMC or DOI page, or a PDF, then click again.");

  let pdf = null;
  if (what.kind === "pdf") {
    report("Reading the PDF from this tab…");
    const r = await fetch(tab.url, { credentials: "include" });
    const bytes = new Uint8Array(await r.arrayBuffer());
    report("Building from the PDF…");
    const job = await postPdf(api, "/api/jobs/pdf", bytes, tab.title?.replace(/[^\w.-]+/g, "_").slice(0, 60) + ".pdf" || "paper.pdf");
    const done = await waitForJob(api, job.id, (j) => report(`Building: ${j.step}…`));
    return `${web}/paper/${encodeURIComponent(done.paper_id)}`;
  }

  report("Looking for the PDF on this page…");
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: pdfFromPage });
    pdf = res?.result || null;
  } catch {
    pdf = null;
  }

  report("Building the explainer…");
  const r = await fetch(`${api}/api/jobs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ input: what.url }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  const job = await r.json();
  const done = await waitForJob(api, job.id, (j) => report(`Building: ${j.step}…`));

  if (pdf) {
    report("Attaching the PDF…");
    try {
      await postPdf(api, `/api/pdf/${encodeURIComponent(done.paper_id)}`, bytesOf(pdf.base64), "paper.pdf");
    } catch (e) {
      report(`Built; the PDF could not be attached (${e.message}).`);
    }
  }
  return `${web}/paper/${encodeURIComponent(done.paper_id)}`;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "run") return false;
  (async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const url = await run(tab, (text) => chrome.runtime.sendMessage({ type: "step", text }).catch(() => {}));
      await chrome.tabs.create({ url });
      sendResponse({ ok: true, url });
    } catch (e) {
      sendResponse({ ok: false, error: e.message || String(e) });
    }
  })();
  return true;
});
