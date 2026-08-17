"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";

type Props = {
  title?: string;
  subtitle?: string;
  pageNumber: number;
  numPages: number;
  onPrev: () => void;
  onNext: () => void;
  onJump: (page: number) => void;
  pdfUrl?: string;
};

export default function PdfToolbar({
  title = "Owner Manual",
  subtitle = "",
  pageNumber,
  numPages,
  onPrev,
  onNext,
  onJump,
  pdfUrl,
}: Props) {
  const [inputValue, setInputValue] = useState(pageNumber.toString());
  const [lastPage, setLastPage] = useState(pageNumber);

  // Scrolling changes the page under us, so the box follows. Adjusted during
  // render rather than in an effect — no second pass, and no cascading render.
  if (pageNumber !== lastPage) {
    setLastPage(pageNumber);
    setInputValue(pageNumber.toString());
  }

  const handleSubmit = () => {
    const page = Number(inputValue);

    if (!Number.isNaN(page) && page >= 1 && page <= numPages) {
      onJump(page);
    } else {
      setInputValue(pageNumber.toString());
    }
  };

  const handleOpenPdf = () => {
    if (!pdfUrl) return;
    window.open(`${pdfUrl}#page=${pageNumber}`, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-base font-semibold text-slate-900" title={title}>
          {title}
        </h2>
        {subtitle ? (
          <p className="truncate text-sm text-slate-500" title={subtitle}>
            {subtitle}
          </p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <button
          onClick={handleOpenPdf}
          disabled={!pdfUrl}
          title="Open PDF in new tab"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ExternalLink size={16} />
          <span>Open</span>
        </button>

        <button
          onClick={onPrev}
          disabled={pageNumber <= 1}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Prev
        </button>

        <div className="flex items-center gap-1 text-sm">
          <input
            type="number"
            min={1}
            max={numPages || 1}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onBlur={handleSubmit}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            className="w-14 rounded-md border border-slate-300 px-2 py-1 text-center outline-none focus:border-slate-400"
          />
          <span className="whitespace-nowrap text-slate-500">/ {numPages || 0}</span>
        </div>

        <button
          onClick={onNext}
          disabled={pageNumber >= numPages || numPages === 0}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}