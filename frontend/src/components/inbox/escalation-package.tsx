"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, NotebookPen, Send, TriangleAlert } from "lucide-react";
import MessageItem from "@/components/chat/message-item";
import { replyToEscalation, type EscalationPackage, type StoredMessage } from "@/lib/api";
import { usePolledMessages } from "@/hooks/use-polled-messages";
import type { Message } from "@/types/chat";

type Props = { pkg: EscalationPackage | null; loading: boolean };

/** The stored transcript rendered through the chat's own component, so the operator reads the
 *  conversation exactly as the user saw it — source badges and citations included (D13). */
function asMessage(stored: StoredMessage): Message {
  return {
    id: stored.id,
    role: stored.role,
    content: stored.content,
    source: (stored.source ?? undefined) as Message["source"],
    citations: stored.citations ?? [],
    steps: [],
    escalation: stored.escalation_id
      ? { id: stored.escalation_id, reason: stored.escalation_reason ?? "", pages: [] }
      : undefined,
  };
}

export default function EscalationPackageView({ pkg, loading }: Props) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Polled while the handoff is open, so the customer's replies arrive without a refresh.
  const polled = usePolledMessages(
    pkg?.session_id ?? null,
    Boolean(pkg) && pkg?.status !== "closed",
  );
  const transcript = polled.length > 0 ? polled : (pkg?.transcript ?? []);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [transcript.length]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!pkg || !text || sending) return;
    setSending(true);
    try {
      await replyToEscalation(pkg.id, text);
      setDraft("");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  }
  if (!pkg) {
    return (
      <p className="p-6 text-sm text-slate-400">
        Select a handoff to see everything the user has already been told.
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-slate-200 px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-sm font-semibold text-slate-900">{pkg.id}</span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            {pkg.status}
          </span>
          <span className="text-[11px] text-slate-400">
            {new Date(pkg.created_at).toLocaleString()}
          </span>
        </div>

        <p className="mt-3 text-base font-medium text-slate-900">{pkg.question}</p>

        {/* The rule that fired, not a constant — D14's triggers each write their own reason. */}
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <p className="text-xs leading-5 text-amber-900">{pkg.reason}</p>
        </div>

        {pkg.pages.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 flex items-center gap-1 text-[11px] font-medium text-slate-500">
              <FileText className="h-3.5 w-3.5" />
              Already shown
            </span>
            {pkg.pages.map((page) => (
              <span
                key={page}
                className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-600"
              >
                p. {page}
              </span>
            ))}
          </div>
        )}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {/* Written by a model and labelled as such. Presenting it as the user's own words is
            the mislabelling D13 exists to prevent. */}
        {pkg.summary && (
          <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wider text-slate-500">
              <NotebookPen className="h-3.5 w-3.5" />
              Issue summary
            </p>
            <p className="text-sm leading-6 text-slate-700">{pkg.summary}</p>
            {pkg.next_step && (
              <p className="mt-3 border-t border-slate-200 pt-3 text-sm leading-6 text-slate-600">
                <span className="font-semibold text-slate-700">Suggested first step: </span>
                {pkg.next_step}
              </p>
            )}
          </div>
        )}

        <p className="mb-3 text-[11px] font-extrabold uppercase tracking-wider text-slate-400">
          The conversation so far
        </p>
        <div className="space-y-5">
          {transcript.map((stored) => (
            <MessageItem key={stored.id} message={asMessage(stored)} viewer="agent" />
          ))}
        </div>
      </div>

      <form
        onSubmit={submit}
        className="flex items-center gap-2 border-t border-slate-200 px-6 py-3"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Reply to the customer…"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-slate-400"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="flex items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-40"
        >
          <Send className="h-3.5 w-3.5" />
          Send
        </button>
      </form>
    </div>
  );
}
