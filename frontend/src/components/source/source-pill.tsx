"use client";

import { ExternalLink, FileText } from "lucide-react";

type Props = {
  kind: "page" | "web";
  label: string;
  title?: string;
  onClick?: () => void;
  href?: string;
};

/**
 * Page and web pills must not look alike. An unmarked general-knowledge answer
 * about a real vehicle is the worst output this system can produce, and
 * identical pills are how that happens (D13).
 */
export default function SourcePill({ kind, label, title, onClick, href }: Props) {
  const shared =
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition active:scale-95";

  if (kind === "web") {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={title}
        className={`${shared} border-dashed border-amber-300 bg-amber-50 text-amber-800 hover:border-amber-400 hover:bg-amber-100`}
      >
        <ExternalLink size={12} />
        {label}
      </a>
    );
  }

  return (
    <button
      onClick={onClick}
      title={title}
      className={`${shared} border-solid border-indigo-200 bg-indigo-50 text-indigo-800 hover:border-indigo-400 hover:bg-indigo-100`}
    >
      <FileText size={12} />
      {label}
    </button>
  );
}
