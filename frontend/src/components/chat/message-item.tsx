"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import StatusPills from "./status-pills";
import SourceList from "@/components/source/source-list";
import type { Message } from "@/types/chat";

type Props = {
  message: Message;
  onPageClick?: (pagePdf: number) => void;
};

/** The badge is the visible half of the guard; the pills are the other half (D13). */
const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  manual: {
    label: "From your manual",
    className: "border-indigo-200 bg-indigo-50 text-indigo-700",
  },
  "manual+general": {
    label: "Manual, partly supplemented",
    className: "border-sky-200 bg-sky-50 text-sky-700",
  },
  general: {
    label: "Not from your manual",
    className: "border-amber-300 bg-amber-50 text-amber-800",
  },
};

const markdownComponents: Components = {
  a: ({ ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-blue-600 underline underline-offset-2 transition hover:text-blue-700"
    />
  ),

  p: ({ children }) => (
    <p className="mb-3 leading-7 text-slate-700 last:mb-0">{children}</p>
  ),

  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),

  h1: ({ children }) => (
    <h1 className="mb-4 mt-2 text-xl font-bold text-slate-900">{children}</h1>
  ),

  h2: ({ children }) => (
    <h2 className="mb-3 mt-4 text-lg font-semibold text-slate-900">
      {children}
    </h2>
  ),

  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-base font-semibold text-slate-900">
      {children}
    </h3>
  ),

  ul: ({ children }) => (
    <ul className="mb-3 ml-5 list-disc space-y-2 text-slate-700">{children}</ul>
  ),

  ol: ({ children }) => (
    <ol className="mb-3 ml-5 list-decimal space-y-2 text-slate-700">
      {children}
    </ol>
  ),

  li: ({ children }) => <li className="pl-1 leading-7">{children}</li>,

  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-4 border-blue-200 bg-blue-50/60 px-4 py-3 text-slate-700 italic">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="my-5 border-slate-200" />,

  code: ({ className, children, ...props }) => {
    const isInline =
      !className ||
      (!className.includes("language-") &&
        String(children).indexOf("\n") === -1);

    if (isInline) {
      return (
        <code
          className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[13px] text-slate-800"
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <pre className="my-4 overflow-x-auto rounded-2xl bg-slate-900 p-4 text-sm text-slate-100 shadow-sm">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    );
  },

  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),

  thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,

  th: ({ children }) => (
    <th className="border-b border-slate-200 px-4 py-2 text-left font-semibold text-slate-800">
      {children}
    </th>
  ),

  td: ({ children }) => (
    <td className="border-b border-slate-100 px-4 py-2 text-slate-700">
      {children}
    </td>
  ),
};

export default function MessageItem({ message, onPageClick }: Props) {
  const isUser = message.role === "user";
  const badge = message.source ? SOURCE_BADGE[message.source] : undefined;

  return (
    <div
      className={`mb-5 flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[85%] rounded-3xl px-5 py-4 transition-all duration-200 ${
          isUser
            ? "rounded-br-md bg-blue-600 text-white shadow-md"
            : "rounded-bl-md border border-slate-200 bg-white shadow-sm"
        }`}
      >
        {!isUser && message.steps.length > 0 && (
          <div className="mb-3">
            <StatusPills steps={message.steps} active={Boolean(message.streaming)} />
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap text-[15px] font-medium leading-7 text-white">
            {message.content}
          </p>
        ) : (
          <div className="max-w-none text-[15px]">
            {message.content ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {message.content}
              </ReactMarkdown>
            ) : message.streaming ? (
              <div className="flex items-center gap-1 py-1">
                <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
                <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
                <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
              </div>
            ) : null}
          </div>
        )}

        {!isUser && badge && !message.failed && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <span
              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${badge.className}`}
            >
              {badge.label}
            </span>
            <SourceList citations={message.citations} onPageClick={onPageClick} />
          </div>
        )}
      </div>
    </div>
  );
}
