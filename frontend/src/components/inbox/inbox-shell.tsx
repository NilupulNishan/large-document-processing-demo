"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Inbox } from "lucide-react";
import EscalationList from "./escalation-list";
import EscalationPackageView from "./escalation-package";
import { listEscalations, loadEscalation, type EscalationPackage } from "@/lib/api";
import type { EscalationSummary } from "@/types/chat";

export default function InboxShell() {
  const [items, setItems] = useState<EscalationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [pkg, setPkg] = useState<EscalationPackage | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);

  // A reference can be deep-linked, so /inbox?id=ESC-XXXXXX opens straight to it.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("id");
    listEscalations()
      .then((found) => {
        setItems(found);
        const first = found.find((item) => item.id === wanted) ?? found[0];
        if (first) setSelected(first.id);
      })
      .catch(() => setItems([]));
  }, []);

  // `cancelled` guards against a slow response for an earlier selection landing last and
  // overwriting a newer one.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    loadEscalation(selected)
      .then((found) => !cancelled && setPkg(found))
      .catch(() => !cancelled && setPkg(null))
      .finally(() => !cancelled && setLoadedId(selected));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  // Derived rather than stored: a loading flag set in the effect body is a cascading render.
  const loading = selected !== null && loadedId !== selected;

  return (
    <div className="h-screen w-full overflow-hidden bg-slate-100">
      <div className="flex h-full gap-4 overflow-hidden bg-white p-4">
        <aside className="flex w-80 shrink-0 flex-col rounded-xl bg-slate-50 p-3">
          <div className="mb-3 flex items-center justify-between px-1">
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Inbox className="h-4 w-4" />
              Handoffs
            </span>
            <span className="text-[11px] text-slate-400">{items.length}</span>
          </div>

          <Link
            href="/"
            className="mb-3 flex items-center gap-1.5 px-1 text-xs text-slate-500 transition hover:text-slate-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to chat
          </Link>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <EscalationList items={items} selected={selected} onSelect={setSelected} />
          </div>
        </aside>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden rounded-xl border border-slate-200">
          <EscalationPackageView pkg={pkg} loading={loading} />
        </main>
      </div>
    </div>
  );
}
