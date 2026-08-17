"use client";

import SourcePill from "./source-pill";
import type { Citation } from "@/types/chat";

type Props = {
  citations: Citation[];
  onPageClick?: (pagePdf: number) => void;
};

/**
 * Two chunks from the same page produce two citations. Shown as-is they look
 * like duplicate pills that navigate to the same place, so they merge and their
 * sections join into the tooltip.
 */
function mergePages(citations: Citation[]) {
  const byPage = new Map<number, { printed?: number | null; sections: string[] }>();

  for (const citation of citations) {
    if (citation.type !== "page") continue;
    const existing = byPage.get(citation.page_pdf) ?? {
      printed: citation.page_printed,
      sections: [],
    };
    if (citation.section) existing.sections.push(citation.section);
    byPage.set(citation.page_pdf, existing);
  }

  return [...byPage.entries()].sort((a, b) => a[0] - b[0]);
}

function domain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function SourceList({ citations, onPageClick }: Props) {
  const pages = mergePages(citations);
  const web = citations.filter((citation) => citation.type === "web");

  if (pages.length === 0 && web.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {pages.map(([pagePdf, { printed, sections }]) => (
        <SourcePill
          key={`page-${pagePdf}`}
          kind="page"
          label={`p. ${printed ?? pagePdf}`}
          title={sections.join("  ·  ") || undefined}
          onClick={() => onPageClick?.(pagePdf)}
        />
      ))}

      {web.map((citation) =>
        citation.type === "web" ? (
          <SourcePill
            key={citation.url}
            kind="web"
            label={domain(citation.url)}
            title={citation.title ?? citation.url}
            href={citation.url}
          />
        ) : null,
      )}
    </div>
  );
}
