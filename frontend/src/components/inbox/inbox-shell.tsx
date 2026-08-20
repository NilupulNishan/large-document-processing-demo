"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox } from "lucide-react";
import AppHeader from "@/components/layout/app-header";
import EscalationList from "./escalation-list";
import EscalationPackageView from "./escalation-package";
import { listEscalations, loadEscalation, type EscalationPackage } from "@/lib/api";
import type { EscalationSummary } from "@/types/chat";

export default function InboxShell() {
  const [items, setItems] = useState<EscalationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [pkg, setPkg] = useState<EscalationPackage | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"open" | "picked_up" | "closed">("open");

  const refresh = useCallback(
    () => listEscalations().then(setItems).catch(() => setItems([])),
    [],
  );

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

  const counts = useMemo(
    () => ({
      open: items.filter((item) => item.status === "open").length,
      picked_up: items.filter((item) => item.status === "picked_up").length,
      closed: items.filter((item) => item.status === "closed").length,
    }),
    [items],
  );
  const shown = useMemo(
    () => items.filter((item) => item.status === filter),
    [items, filter],
  );

  const waiting = items.filter((item) => item.status === "open").length;

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-ground">
      <AppHeader variant="agent" openHandoffs={waiting} />

      <div className="flex min-h-0 flex-1 gap-4 overflow-hidden bg-surface p-4">
        <aside className="flex w-80 shrink-0 flex-col rounded-lg border border-divider bg-raised p-3">
          <div className="mb-3 flex items-center justify-between px-1">
            <span className="flex items-center gap-2 text-body font-semibold text-ink">
              <Inbox className="h-4 w-4" strokeWidth={1.7} />
              Handoffs
            </span>
            <span className="text-small text-ink-3">{items.length}</span>
          </div>

          <div className="mb-3 flex gap-1.5">
            {(
              [
                ["open", "Open"],
                ["picked_up", "Picked up"],
                ["closed", "Closed"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                aria-pressed={filter === key}
                className={`h-7 rounded-full px-2.5 text-small font-semibold transition-colors ${
                  filter === key
                    ? "bg-ink text-white"
                    : "border border-line text-ink-2 hover:bg-surface"
                }`}
              >
                {label} {counts[key]}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <EscalationList items={shown} selected={selected} onSelect={setSelected} />
          </div>
        </aside>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-divider">
          <EscalationPackageView
            pkg={pkg}
            loading={loading}
            onStatusChange={refresh}
          />
        </main>
      </div>
    </div>
  );
}
