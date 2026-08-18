"use client";

import { useState } from "react";
import Link from "next/link";
import { Inbox, Trash2 } from "lucide-react";
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
    <aside className="hidden h-full w-72 shrink-0 flex-col rounded-2xl border border-slate-200 bg-slate-50 p-5 lg:flex">
      <div className="mb-6 px-1">
        {/* Named for what it does, not for whose manuals happen to be loaded. */}
        <h1 className="text-lg font-black tracking-tight text-slate-900">
          Manual <span className="text-blue-600">Assist</span>
        </h1>
        <p className="mt-0.5 text-[10px] font-bold uppercase tracking-widest text-slate-400">
          Answers with the page
        </p>
      </div>

      <button
        onClick={onNewChat}
        disabled={!selectedManual}
        className="mb-6 w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white transition hover:bg-blue-600 active:scale-95 disabled:opacity-40"
      >
        + New conversation
      </button>

      <p className="mb-2 px-1 text-[11px] font-extrabold uppercase tracking-wider text-slate-400">
        Manual
      </p>
      <div className="mb-6 space-y-1.5">
        {manuals.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
            No manuals indexed.
          </p>
        ) : (
          manuals.map((manual) => (
            <button
              key={manual.id}
              onClick={() => onSelectManual(manual.id)}
              className={`w-full rounded-lg border px-4 py-3 text-left text-sm transition ${
                manual.id === selectedManual
                  ? "border-slate-200 bg-white font-bold text-blue-600 shadow-sm"
                  : "border-transparent text-slate-600 hover:border-slate-200 hover:bg-white"
              }`}
            >
              <span className="block truncate">{manual.title}</span>
              <span className="text-[11px] font-normal text-slate-400">
                {manual.page_count} pages
              </span>
            </button>
          ))
        )}
      </div>

      <p className="mb-2 px-1 text-[11px] font-extrabold uppercase tracking-wider text-slate-400">
        History
      </p>
      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
        {sessions.length === 0 ? (
          <p className="px-1 text-xs text-slate-400">Nothing yet.</p>
        ) : (
          sessions.map((session) => {
            const armed = session.id === confirming;
            return (
              // A div, not a button: the delete control cannot be nested inside the select
              // button, and a button inside a button is invalid HTML.
              <div
                key={session.id}
                className={`group flex items-center rounded-lg transition ${
                  session.id === selectedSession
                    ? "bg-white shadow-sm"
                    : "hover:bg-white"
                }`}
              >
                {armed ? (
                  <div className="flex w-full items-center gap-1 px-3 py-2">
                    <span className="flex-1 truncate text-xs text-slate-500">Delete?</span>
                    <button
                      onClick={() => {
                        setConfirming(null);
                        onDeleteSession(session.id);
                      }}
                      className="rounded px-2 py-0.5 text-xs font-semibold text-red-600 transition hover:bg-red-50"
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setConfirming(null)}
                      className="rounded px-2 py-0.5 text-xs text-slate-500 transition hover:bg-slate-100"
                    >
                      No
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onSelectSession(session.id)}
                      title={session.title}
                      className={`min-w-0 flex-1 px-3 py-2 text-left text-xs transition ${
                        session.id === selectedSession
                          ? "font-semibold text-slate-900"
                          : "text-slate-500 group-hover:text-slate-800"
                      }`}
                    >
                      <span className="block truncate">{session.title}</span>
                    </button>
                    <button
                      onClick={() => setConfirming(session.id)}
                      aria-label={`Delete ${session.title}`}
                      title="Delete this conversation"
                      className="mr-1 rounded p-1.5 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 focus:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>

      <Link
        href="/inbox"
        className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-500 transition hover:bg-white hover:text-slate-800"
      >
        <Inbox className="h-3.5 w-3.5" />
        Operator inbox
      </Link>
    </aside>
  );
}
