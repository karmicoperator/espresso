"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ExplainerReader } from "@/components/ExplainerReader";
import type { Explainer } from "@/lib/types";

export default function PaperPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const paperId = decodeURIComponent(id);
  const [explainer, setExplainer] = useState<Explainer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get(paperId).then(setExplainer).catch((e) => setError(e.message));
  }, [paperId]);

  if (error) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-24">
        <p className="rounded-xl border border-[#f27066]/30 bg-[#f27066]/10 p-4 text-sm text-[#f27066]">
          {error}
        </p>
        <Link href="/" className="mt-6 inline-block text-sm text-white/60 hover:text-white">
          ← Build another paper
        </Link>
      </main>
    );
  }

  if (!explainer) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-24">
        <p className="text-sm text-white/55">Loading…</p>
      </main>
    );
  }

  return <ExplainerReader explainer={explainer} />;
}
