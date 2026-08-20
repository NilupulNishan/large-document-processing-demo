"use client";

import Link from "next/link";
import { ArrowLeft, ChevronDown, FileText, Inbox } from "lucide-react";
import type { Manual } from "@/types/chat";

type Props = {
  /** The operator side is a different context and says so. */
  variant?: "assistant" | "agent";
  manuals?: Manual[];
  selectedManual?: string | null;
  onSelectManual?: (id: string) => void;
  openHandoffs?: number;
};

/**
 * The app's only h1, and the only navigation that survives the width at which the
 * sidebar is hidden. Green marks the operator side because green already means a person
 * is involved — the palette gains no sixth colour for it.
 */
export default function AppHeader({
  variant = "assistant",
  manuals = [],
  selectedManual = null,
  onSelectManual,
  openHandoffs = 0,
}: Props) {
  const agent = variant === "agent";
  const manual = manuals.find((item) => item.id === selectedManual) ?? null;

  return (
    <header
      className={`flex h-13 shrink-0 items-center gap-2.5 border-b border-line bg-surface px-4 ${
        agent ? "border-t-[3px] border-t-person" : ""
      }`}
    >
      <div className="flex items-center gap-2.5 pr-1.5">
        <FileText
          className={`h-5 w-5 ${agent ? "text-person" : "text-action"}`}
          strokeWidth={1.6}
        />
        <h1 className="text-sm font-bold tracking-tight">
          {agent ? "Agent portal" : "Manual Assist"}
        </h1>
        {agent && (
          <span className="rounded-full bg-person-soft px-2 py-0.5 text-small font-bold text-person">
            Staff
          </span>
        )}
      </div>

      <div className="h-5.5 w-px bg-divider" />

      {agent ? (
        <span className="text-body text-ink-2">
          {openHandoffs} waiting
        </span>
      ) : (
        // The manual is app-level scope, so it is named here and switched in the sidebar.
        // Both read the same selection; they can never disagree.
        <div className="relative">
          <select
            aria-label="Manual"
            value={selectedManual ?? ""}
            onChange={(event) => onSelectManual?.(event.target.value)}
            disabled={manuals.length === 0}
            className="h-8.5 appearance-none rounded border border-line bg-surface py-0 pl-2.5 pr-8 text-body font-semibold text-ink hover:bg-raised disabled:text-ink-3"
          >
            {manuals.length === 0 && <option value="">No manuals indexed</option>}
            {manuals.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-2"
            strokeWidth={2}
          />
        </div>
      )}

      {manual && !agent && (
        <span className="text-small text-ink-3">{manual.page_count} pages</span>
      )}

      <div className="flex-1" />

      {agent ? (
        <Link
          href="/"
          className="flex h-8.5 items-center gap-2 rounded px-2.5 text-body text-ink-2 hover:bg-raised hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.7} />
          Back to the assistant
        </Link>
      ) : (
        <Link
          href="/inbox"
          className="flex h-8.5 items-center gap-2 rounded px-2.5 text-body text-ink-2 hover:bg-raised hover:text-ink"
        >
          <Inbox className="h-4 w-4" strokeWidth={1.6} />
          Operator inbox
          {openHandoffs > 0 && (
            <span className="min-w-4.5 rounded-full bg-person px-1.5 text-center text-small font-bold leading-4.5 text-white">
              {openHandoffs}
            </span>
          )}
        </Link>
      )}
    </header>
  );
}
