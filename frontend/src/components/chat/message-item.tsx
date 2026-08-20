"use client";

import { useState } from "react";
import { Check, ChevronDown, UserRound } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import StatusPills from "./status-pills";
import SourceList from "@/components/source/source-list";
import type { Message } from "@/types/chat";

type Props = {
  message: Message;
  onPageClick?: (pagePdf: number) => void;
  /** Whose seat the thread is being read from. The inbox reads it as the agent (D24). */
  viewer?: "user" | "agent";
};

/** The badge is the visible half of the guard; the pills are the other half (D13). */
const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  manual: {
    label: "From your manual",
    className: "border-manual-line bg-manual-soft text-manual",
  },
  "manual+general": {
    label: "Manual, partly supplemented",
    className: "border-dashed border-general-line bg-manual-soft text-manual",
  },
  general: {
    label: "Not from your manual",
    className: "border-dashed border-general-line bg-general-soft text-general",
  },
};

const markdownComponents: Components = {
  a: ({ ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="font-semibold text-action underline underline-offset-2 hover:text-action-hover"
    />
  ),

  p: ({ children }) => <p className="mb-3 leading-6 last:mb-0">{children}</p>,

  strong: ({ children }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),

  h1: ({ children }) => (
    <h1 className="mb-3 mt-2 text-md font-bold text-ink">{children}</h1>
  ),

  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-sm font-bold text-ink">{children}</h2>
  ),

  h3: ({ children }) => (
    <h3 className="mb-2 mt-3 text-xs font-bold text-ink">{children}</h3>
  ),

  ul: ({ children }) => (
    <ul className="mb-3 ml-4 list-disc space-y-1.5">{children}</ul>
  ),

  ol: ({ children }) => (
    <ol className="mb-3 ml-4 list-decimal space-y-1.5">{children}</ol>
  ),

  li: ({ children }) => <li className="pl-1 leading-6">{children}</li>,

  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-manual-line bg-manual-soft px-3 py-2">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="my-4 border-divider" />,

  code: ({ className, children, ...props }) => {
    const isInline =
      !className ||
      (!className.includes("language-") &&
        String(children).indexOf("\n") === -1);

    if (isInline) {
      return (
        <code
          className="rounded bg-raised px-1.5 py-0.5 font-mono text-small text-ink"
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <pre className="my-3 overflow-x-auto rounded border border-divider bg-raised p-3 font-mono text-small">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    );
  },

  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded border border-divider">
      <table className="min-w-full border-collapse text-body">{children}</table>
    </div>
  ),

  thead: ({ children }) => <thead className="bg-raised">{children}</thead>,

  th: ({ children }) => (
    <th className="border-b border-divider px-3 py-2 text-left font-semibold text-ink">
      {children}
    </th>
  ),

  td: ({ children }) => (
    <td className="border-b border-divider px-3 py-2 text-ink-2">{children}</td>
  ),
};

export default function MessageItem({ message, onPageClick, viewer = "user" }: Props) {
  const isUser = message.role === "user";
  // A human's turn, not the assistant's. Rendered differently on purpose: the user must never
  // have to guess whether they are talking to a person (D24).
  const isAgent = message.role === "agent";
  // The same thread is read from two seats. Whoever is looking sits on the right, so an agent
  // does not see their own replies in the customer's position.
  const mine = message.role === viewer;
  const badge = message.source ? SOURCE_BADGE[message.source] : undefined;
  const [openTrace, setOpenTrace] = useState(false);

  // A trace is worth the room while it is happening. Afterwards it is provenance, and one
  // line of it is enough until asked.
  const streaming = Boolean(message.streaming);
  const showTrace = message.steps.length > 0 && (streaming || openTrace);

  // Typed turns keep a bubble; a long-form answer does not, because tables and code blocks
  // do not fit inside 85% of a pane (audit 16).
  if (isUser || isAgent) {
    return (
      <div className={`flex w-full ${mine ? "justify-end" : "justify-start"}`}>
        <div
          className={`max-w-[80%] rounded-lg px-3.5 py-2.5 text-body transition-colors ${
            mine
              ? isAgent
                ? "rounded-br-sm bg-person text-white"
                : "rounded-br-sm bg-action text-white"
              : isAgent
                ? "rounded-bl-sm border border-person-line bg-person-soft"
                : "rounded-bl-sm border border-divider bg-surface"
          }`}
        >
          {isAgent && !mine && (
            <div className="mb-1.5 flex items-center gap-1.5 text-small font-semibold text-person">
              <UserRound className="h-3 w-3" />
              Support agent
            </div>
          )}
          {/* Human-typed turns render verbatim. Markdown is for the assistant, which is asked
              to produce it; a person's stray asterisk should not become italics. */}
          <p className="whitespace-pre-wrap leading-5">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-enter w-full">
      {message.steps.length > 0 && !streaming && (
        <button
          onClick={() => setOpenTrace((open) => !open)}
          aria-expanded={openTrace}
          className="mb-3 inline-flex items-center gap-2 rounded-full border border-divider bg-raised py-1 pl-1.5 pr-2.5 text-small text-ink-2 hover:bg-ground"
        >
          <Check className="h-3.5 w-3.5 text-person" strokeWidth={2.5} />
          {message.steps.length} steps
          {message.elapsedMs !== undefined && (
            <span className="text-ink-3">· {(message.elapsedMs / 1000).toFixed(1)}s</span>
          )}
          <ChevronDown
            className={`h-3 w-3 text-ink-3 transition-transform ${openTrace ? "rotate-180" : ""}`}
            strokeWidth={2}
          />
        </button>
      )}

      {showTrace && (
        <div className="mb-4">
          <StatusPills steps={message.steps} active={streaming} />
        </div>
      )}

      <div className="text-body text-ink">
        {message.content ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {message.content}
          </ReactMarkdown>
        ) : streaming && message.steps.length === 0 ? (
          <span className="animate-caret inline-block h-4 w-0.5 bg-action align-middle" />
        ) : null}
      </div>

      {badge && !message.failed && (
        <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-divider pt-3">
          <span
            className={`rounded border px-2 py-0.5 text-small font-semibold ${badge.className}`}
          >
            {badge.label}
          </span>
          <SourceList citations={message.citations} onPageClick={onPageClick} />
        </div>
      )}

      {/* No source badge and no citations: a handoff is not an answer (D12). */}
      {message.escalation && (
        <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-divider pt-3">
          <span className="inline-flex items-center gap-1.5 rounded border border-person-line bg-person-soft px-2 py-0.5 text-small font-semibold text-person">
            <UserRound className="h-3 w-3" />
            Passed to a specialist
          </span>
          <span className="rounded bg-raised px-2 py-0.5 font-mono text-small text-ink-2">
            {message.escalation.id}
          </span>
          {message.escalation.reason && (
            <span className="text-small text-ink-3">{message.escalation.reason}</span>
          )}
        </div>
      )}
    </div>
  );
}
