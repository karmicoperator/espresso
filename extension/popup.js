// The popup: says what the current page is, runs the build on a click, follows its steps.
const $ = (id) => document.getElementById(id);

function describe(url) {
  try {
    const u = new URL(url);
    if (u.pathname.toLowerCase().endsWith(".pdf")) return "A PDF. It will be built from this file.";
    if (/PMC\d{4,}/.test(url)) return "A PubMed Central paper. The full text is read from PMC; the PDF on this page is attached if it can be fetched.";
    if (u.hostname.endsWith("ncbi.nlm.nih.gov")) return "A PubMed page. Built from PubMed Central's full text.";
    if (u.hostname === "doi.org" || u.pathname.includes("/10.")) return "A DOI page. Built from PubMed Central's full text when the paper is there; the PDF here is attached if it can be fetched.";
    return "";
  } catch {
    return "";
  }
}

(async () => {
  const s = await chrome.storage.local.get({ api: "http://localhost:8000", web: "http://localhost:3000" });
  $("api").value = s.api;
  $("web").value = s.web;
  for (const id of ["api", "web"]) {
    $(id).addEventListener("change", () => chrome.storage.local.set({ [id]: $(id).value.trim() || (id === "api" ? "http://localhost:8000" : "http://localhost:3000") }));
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const what = describe(tab?.url || "");
  $("what").textContent = what || "Not a paper page. Open a PubMed, PMC or DOI page, or a PDF.";
  $("go").disabled = !what;
})();

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "step") {
    $("status").className = "status";
    $("status").textContent = msg.text;
  }
});

$("go").addEventListener("click", () => {
  $("go").disabled = true;
  $("status").className = "status";
  $("status").textContent = "Starting…";
  chrome.runtime.sendMessage({ type: "run" }, (res) => {
    if (chrome.runtime.lastError || !res?.ok) {
      $("status").className = "status err";
      $("status").textContent = res?.error || chrome.runtime.lastError?.message || "Something went wrong.";
      $("go").disabled = false;
      return;
    }
    $("status").innerHTML = `Built. <a href="${res.url}" target="_blank">Open it</a>`;
    $("go").disabled = false;
  });
});
