"use client";

import { useEffect, useRef, useState } from "react";
import {
  CircleCheck,
  FileText,
  NotebookPen,
  Send,
  TriangleAlert,
} from "lucide-react";
import MessageItem from "@/components/chat/message-item";
import MicButton from "@/components/chat/mic-button";
import {
  replyToEscalation,
  setEscalationStatus,
  type EscalationPackage,
  type StoredMessage,
} from "@/lib/api";
import { useDictation } from "@/hooks/use-dictation";
import { usePolledMessages } from "@/hooks/use-polled-messages";
import type { Message } from "@/types/chat";

type Props = {
  pkg: EscalationPackage | null;
  loading: boolean;
  /** Lets the list re-read the queue once a status moves. */
  onStatusChange?: () => void;
};

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
      ? {
          id: stored.escalation_id,
          reason: stored.escalation_reason ?? "",
          pages: [],
        }
      : undefined,
  };
}

export default function EscalationPackageView({
  pkg,
  loading,
  onStatusChange,
}: Props) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // Shown at once so the button is not dead while the request is in flight; the server
  // value replaces it on the next load.
  const [movedTo, setMovedTo] = useState<EscalationPackage["status"] | null>(
    null,
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  // Dictated words are appended, never substituted, so a half-typed reply survives.
  const dictation = useDictation((text) =>
    setDraft((current) => (current ? `${current.trimEnd()} ${text}` : text)),
  );

  // Polled while the handoff is open, so the customer's replies arrive without a refresh.
  const polled = usePolledMessages(
    pkg?.session_id ?? null,
    Boolean(pkg) && pkg?.status !== "closed",
  );
  const transcript =
    polled.messages.length > 0 ? polled.messages : (pkg?.transcript ?? []);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [transcript.length]);

  // Adjusted during render rather than in an effect, as pdf-toolbar does: selecting a
  // different handoff drops any optimistic status from the previous one. Both sides are
  // normalised to null first — comparing `undefined` against a stored `null` never settles
  // and spins the renderer.
  const currentId = pkg?.id ?? null;
  const [lastId, setLastId] = useState(currentId);
  if (currentId !== lastId) {
    setLastId(currentId);
    setMovedTo(null);
  }

  // Closing hands the conversation back to the pipeline, so replying after it would be a
  // person speaking into a conversation no person is in. The server refuses it too (409).
  const closed = (movedTo ?? pkg?.status) === "closed";

  async function move(status: EscalationPackage["status"]) {
    if (!pkg) return;
    setMovedTo(status);
    try {
      await setEscalationStatus(pkg.id, status);
      onStatusChange?.();
    } catch {
      setMovedTo(null);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!pkg || !text || sending || closed || dictation.interim) return;
    setSending(true);
    try {
      await replyToEscalation(pkg.id, text);
      setDraft("");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <p className="p-6 text-body text-ink-3">Loading…</p>;
  }
  if (!pkg) {
    return (
      <p className="p-6 text-body text-ink-3">
        Select a handoff to see everything the user has already been told.
      </p>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-divider px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-body font-semibold text-ink">
            {pkg.id}
          </span>
          <span className="rounded border border-divider bg-raised px-2 py-0.5 text-small font-semibold text-ink-2">
            {(movedTo ?? pkg.status).replace("_", " ")}
          </span>
          <span className="text-small text-ink-3">
            {new Date(pkg.created_at).toLocaleString()}
          </span>

          <span className="ml-auto flex items-center gap-2">
            {(movedTo ?? pkg.status) !== "picked_up" && (
              <button
                onClick={() => move("picked_up")}
                className="h-8 rounded bg-person px-3 text-body font-semibold text-white transition-colors hover:brightness-110"
              >
                {closed ? "Reopen" : "Pick up"}
              </button>
            )}
            {(movedTo ?? pkg.status) !== "closed" && (
              <button
                onClick={() => move("closed")}
                className="h-8 rounded border border-line px-3 text-body font-semibold text-ink transition-colors hover:bg-raised"
              >
                Close
              </button>
            )}
          </span>
        </div>

        <p className="mt-3 text-sm font-semibold text-ink">{pkg.question}</p>

        {/* The rule that fired, not a constant — D14's triggers each write their own reason. */}
        <div className="mt-3 flex items-start gap-2 rounded border border-general-line bg-general-soft px-3 py-2">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-general" />
          <p className="text-small leading-4 text-general">{pkg.reason}</p>
        </div>

        {pkg.pages.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 flex items-center gap-1 text-small font-semibold text-ink-2">
              <FileText className="h-3.5 w-3.5" />
              Already shown
            </span>
            {pkg.pages.map((page) => (
              <span
                key={page}
                className="rounded border border-divider bg-surface px-2 py-0.5 text-small text-ink-2"
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
          <div className="mb-5 rounded border border-divider bg-raised p-4">
            <p className="mb-2 flex items-center gap-1.5 text-small font-bold uppercase tracking-wide text-ink-2">
              <NotebookPen className="h-3.5 w-3.5" />
              Issue summary
            </p>
            <p className="text-body leading-5 text-ink">{pkg.summary}</p>
            {pkg.next_step && (
              <p className="mt-3 border-t border-divider pt-3 text-body leading-5 text-ink-2">
                <span className="font-semibold text-ink">
                  Suggested first step:{" "}
                </span>
                {pkg.next_step}
              </p>
            )}
          </div>
        )}

        <p className="mb-3 text-small font-bold uppercase tracking-wide text-ink-3">
          The conversation so far
        </p>
        <div className="space-y-5">
          {transcript.map((stored) => (
            <MessageItem
              key={stored.id}
              message={asMessage(stored)}
              viewer="agent"
            />
          ))}
        </div>
      </div>

      {closed ? (
        <p className="flex items-center gap-2 border-t border-divider px-6 py-4 text-body text-ink-2">
          <CircleCheck
            className="h-4 w-4 shrink-0 text-ink-3"
            strokeWidth={1.7}
          />
          This handoff is closed. The assistant has the conversation again —
          pick it up to reply.
        </p>
      ) : (
        <form
          onSubmit={submit}
          className="flex items-start gap-2 border-t border-divider px-6 py-3"
        >
          <div className="min-w-0 flex-1">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Reply to the customer…"
              className="h-9 w-full rounded border border-line px-3 text-body text-ink outline-none transition-colors focus:border-person"
            />
            {(dictation.interim || dictation.error || dictation.state !== "idle") && (
              <p className="mt-1.5 truncate text-small text-ink-2">
                {dictation.interim ? (
                  <span className="animate-breathe">{dictation.interim}</span>
                ) : dictation.error ? (
                  <span className="text-general">{dictation.error}</span>
                ) : dictation.state === "listening" ? (
                  "Listening, press stop when you are done"
                ) : (
                  "Opening the microphone"
                )}
              </p>
            )}
          </div>

          <MicButton
            state={dictation.state}
            onStart={dictation.start}
            onStop={dictation.stop}
          />

          <button
            type="submit"
            disabled={
              sending ||
              !draft.trim() ||
              dictation.state !== "idle" ||
              Boolean(dictation.interim)
            }
            className="flex h-9 items-center gap-1.5 rounded bg-person px-3.5 text-body font-semibold text-white transition-colors hover:brightness-110 disabled:bg-divider disabled:text-ink-4"
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </button>
        </form>
      )}
    </div>
  );
}
