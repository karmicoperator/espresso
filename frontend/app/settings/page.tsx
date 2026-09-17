"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api";
import type { SettingsView } from "@/lib/types";

const ORDER = ["claude_cli", "anthropic", "openai", "azure"];

/**
 * Which model builds the papers. Saved to backend/.env by the API, so a hand edit and
 * this page agree. The key is sent once, on save, and never comes back: the page only
 * learns that one is set and its last four characters.
 */
export default function SettingsPage() {
  const [view, setView] = useState<SettingsView | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "test">("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  function adopt(v: SettingsView, which?: string) {
    const name = which ?? (v.provider || "claude_cli");
    const p = v.providers[name];
    setView(v);
    setProvider(name);
    setModel(p?.model ?? "");
    setBaseUrl(p?.base_url ?? "");
    setEndpoint(p?.endpoint ?? "");
    setApiKey("");
  }

  useEffect(() => {
    api.settings().then((v) => adopt(v)).catch((e) => setNote({ ok: false, text: e.message }));
  }, []);

  async function save() {
    setBusy("save");
    setNote(null);
    try {
      const v = await api.saveSettings({ provider, model, api_key: apiKey, base_url: baseUrl, endpoint });
      adopt(v, provider);
      setNote({ ok: true, text: `Saved to ${v.env_path}. Test it to be sure it answers.` });
    } catch (e) {
      setNote({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy("");
    }
  }

  async function test() {
    setBusy("test");
    setNote(null);
    try {
      const r = await api.testSettings();
      setNote({ ok: r.ok, text: r.message });
    } catch (e) {
      setNote({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy("");
    }
  }

  const p = view?.providers[provider];
  const dirty = view !== null && (provider !== view.provider || apiKey !== "" || model !== (p?.model ?? "") ||
    baseUrl !== (p?.base_url ?? "") || endpoint !== (p?.endpoint ?? ""));

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <Link href="/" className="text-xs text-white/50 transition-colors hover:text-white">
        ← Back
      </Link>
      <h1 className="mt-5 text-2xl font-medium tracking-tight text-[#e8e8e8]">Model</h1>
      <p className="mt-2 text-sm leading-relaxed text-white/50">
        Which model reads the paper and chooses the charts. Every number it produces is
        still checked against the paper, whichever you pick.
      </p>

      {view?.problem && (
        <p className="mt-5 rounded-xl border border-[#d9a441]/25 bg-[#d9a441]/[0.06] px-4 py-3 text-xs text-[#d9a441]">
          {view.problem}
        </p>
      )}

      {view && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="mt-8 space-y-6"
        >
          <fieldset className="space-y-2">
            {ORDER.map((name) => {
              const item = view.providers[name];
              const active = view.provider === name;
              return (
                <label
                  key={name}
                  className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-5 py-4 transition-colors ${
                    provider === name
                      ? "border-white/25 bg-white/[0.06]"
                      : "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.16]"
                  }`}
                >
                  <input
                    type="radio"
                    name="provider"
                    value={name}
                    checked={provider === name}
                    onChange={() => adopt(view, name)}
                    className="mt-1"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm text-[#e8e8e8]">
                      {item.label}
                      {active && <span className="ml-2 text-xs text-[#7dd19b]">in use</span>}
                      {item.needs_key && item.key_set && (
                        <span className="num ml-2 text-xs text-white/35">key …{item.key_hint}</span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-white/40">{item.help}</span>
                  </span>
                </label>
              );
            })}
          </fieldset>

          {p && (
            <div className="space-y-4 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-5 py-5">
              {p.needs_key && (
                <Field
                  label={provider === "azure" ? "API key" : "API key"}
                  hint={p.key_set ? `A key ending …${p.key_hint} is saved. Leave empty to keep it.` : "Pasted once, stored in backend/.env on this machine, never shown again."}
                >
                  <input
                    type="password"
                    autoComplete="off"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={p.key_set ? "•••••••••••••" : provider === "anthropic" ? "sk-ant-…" : "sk-…"}
                    className={inputClass}
                  />
                </Field>
              )}
              {provider === "openai" && (
                <Field
                  label="Base URL"
                  hint="Empty for OpenAI itself. For another provider, its OpenAI-compatible URL, e.g. http://localhost:11434/v1 for Ollama or https://api.groq.com/openai/v1."
                >
                  <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className={inputClass} />
                </Field>
              )}
              {provider === "azure" && (
                <Field label="Endpoint" hint="The resource URL from the Azure portal.">
                  <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://<resource>.openai.azure.com" className={inputClass} />
                </Field>
              )}
              <Field
                label={provider === "azure" ? "Deployment" : "Model"}
                hint={`Empty means ${p.default_model}.`}
              >
                <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={p.default_model} className={inputClass} />
              </Field>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={busy !== "" || !dirty}
              className="rounded-full border border-white/[0.14] bg-white/[0.08] px-5 py-2 text-sm text-[#e8e8e8] transition-colors hover:bg-white/[0.14] disabled:opacity-30"
            >
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => void test()}
              disabled={busy !== "" || dirty}
              title={dirty ? "Save first" : "One tiny call through the saved provider"}
              className="rounded-full border border-white/[0.10] px-5 py-2 text-sm text-white/70 transition-colors hover:border-white/25 hover:text-white disabled:opacity-30"
            >
              {busy === "test" ? "Asking the model…" : "Test"}
            </button>
            {note && (
              <span className={`text-xs ${note.ok ? "text-[#7dd19b]" : "text-[#f27066]"}`} role="status">
                {note.text}
              </span>
            )}
          </div>
        </form>
      )}
    </main>
  );
}

const inputClass =
  "w-full rounded-xl border border-white/[0.10] bg-black/40 px-3.5 py-2 text-sm text-[#e8e8e8] placeholder:text-white/20 focus:border-white/30 focus:outline-none";

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs text-white/60">{label}</span>
      <span className="mt-1.5 block">{children}</span>
      <span className="mt-1.5 block text-xs leading-relaxed text-white/30">{hint}</span>
    </label>
  );
}
