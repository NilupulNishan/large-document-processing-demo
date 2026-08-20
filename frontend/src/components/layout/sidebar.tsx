"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { Manual, SessionSummary } from "@/types/chat";

type Props = {
  manuals: Manual[];
  sessions: SessionSummary[];
  selectedManual: string | null;
  selectedSession: string | null;
  onSelectManual: (id: string) => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewChat: () => void;
};

export default function Sidebar({
  manuals,
  sessions,
  selectedManual,
  selectedSession,
  onSelectManual,
  onSelectSession,
  onDeleteSession,
  onNewChat,
}: Props) {
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <aside className="hidden h-full w-62 shrink-0 flex-col border-r border-divider bg-surface p-3.5 lg:flex">
      <button
        onClick={onNewChat}
        disabled={!selectedManual}
        className="flex h-9 w-full items-center justify-center gap-1.5 rounded bg-action text-body font-semibold text-white transition-colors hover:bg-action-hover disabled:bg-ink-4"
      >
        <Plus className="h-3.5 w-3.5" strokeWidth={2} />
        New conversation
      </button>

      {/* The header names the manual; this is where it changes. Both read one selection. */}
      <p className="mt-5.5 mb-2 px-1 text-small font-bold text-ink-2">Manual</p>
      <div className="flex flex-col gap-0.5">
        {manuals.length === 0 ? (
          <p className="rounded border border-divider px-2.5 py-2 text-body text-ink-3">
            No manuals indexed.
          </p>
        ) : (
          manuals.map((manual) => {
            const active = manual.id === selectedManual;
            return (
              <button
                key={manual.id}
                onClick={() => onSelectManual(manual.id)}
                aria-current={active ? "true" : undefined}
                className={`rounded-r border-l-2 px-2.5 py-2 text-left transition-colors ${
                  active
                    ? "border-action bg-action-soft"
                    : "border-transparent hover:bg-raised"
                }`}
              >
                <span
                  className={`block truncate text-body ${active ? "font-semibold text-ink" : "text-ink"}`}
                >
                  {manual.title}
                </span>
                <span className="text-small text-ink-3">{manual.page_count} pages</span>
              </button>
            );
          })
        )}
      </div>

      <p className="mt-5 mb-2 px-1 text-small font-bold text-ink-2">History</p>
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-y-auto">
        {sessions.length === 0 ? (
          <p className="px-1 text-small text-ink-3">Nothing yet.</p>
        ) : (
          sessions.map((session) => {
            const armed = session.id === confirming;
            const active = session.id === selectedSession;
            return (
              // A div, not a button: the delete control cannot be nested inside the select
              // button, and a button inside a button is invalid HTML.
              <div
                key={session.id}
                className={`group flex items-center rounded transition-colors ${
                  active ? "bg-action-soft" : "hover:bg-raised"
                }`}
              >
                <button
                  onClick={() => onSelectSession(session.id)}
                  title={session.title}
                  className={`min-w-0 flex-1 px-2.5 py-2 text-left text-body ${
                    active ? "font-semibold text-ink" : "text-ink-2 group-hover:text-ink"
                  }`}
                >
                  <span className="block truncate">{session.title}</span>
                </button>

                {/* The name stays visible while confirming: you should be able to see what
                    you are about to delete. */}
                {armed ? (
                  <span className="flex shrink-0 items-center gap-1 pr-1.5">
                    <button
                      onClick={() => {
                        setConfirming(null);
                        onDeleteSession(session.id);
                      }}
                      className="rounded px-1.5 py-0.5 text-small font-semibold text-danger hover:bg-danger/10"
                    >
                      Delete
                    </button>
                    <button
                      onClick={() => setConfirming(null)}
                      className="rounded px-1.5 py-0.5 text-small text-ink-2 hover:bg-divider"
                    >
                      Keep
                    </button>
                  </span>
                ) : (
                  <button
                    onClick={() => setConfirming(session.id)}
                    aria-label={`Delete ${session.title}`}
                    title="Delete this conversation"
                    className="mr-1.5 shrink-0 rounded p-1.5 text-ink-4 opacity-0 transition hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
