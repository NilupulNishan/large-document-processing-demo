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
 *
 * The difference is carried by border style as well as colour — solid against dashed —
 * so it survives greyscale, a printout and a colour-vision deficiency.
 */
export default function SourcePill({ kind, label, title, onClick, href }: Props) {
  const shared =
    "inline-flex h-8 items-center gap-1.5 rounded border px-3.5 text-body font-semibold transition-colors active:scale-95";

  if (kind === "web") {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={title}
        className={`${shared} border-dashed border-general-line bg-general-soft text-general hover:bg-general-soft/70`}
      >
        <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.8} />
        {label}
      </a>
    );
  }

  return (
    <button
      onClick={onClick}
      title={title}
      className={`${shared} border-solid border-manual-line bg-manual-soft text-manual-ink hover:border-manual hover:bg-manual-line/40`}
    >
      <FileText className="h-3.5 w-3.5" strokeWidth={1.8} />
      {label}
    </button>
  );
}
