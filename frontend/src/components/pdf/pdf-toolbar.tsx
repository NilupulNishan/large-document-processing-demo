"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";

type Props = {
  pageNumber: number;
  numPages: number;
  onPrev: () => void;
  onNext: () => void;
  onJump: (page: number) => void;
  pdfUrl?: string;
};

/** The global header names the manual, so this bar only says where you are in it. */
export default function PdfToolbar({
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

  const control =
    "grid h-8 w-8 shrink-0 place-items-center rounded border border-line bg-surface text-ink-2 transition-colors hover:bg-raised disabled:text-ink-4 disabled:hover:bg-surface";

  return (
    <div className="flex items-center gap-2 border-b border-divider bg-surface px-4 py-2.5">
      <p className="min-w-0 flex-1 truncate text-small text-ink-3">
        {numPages ? `Page ${pageNumber} of ${numPages}` : "No document"}
      </p>

      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={onPrev}
          disabled={pageNumber <= 1}
          aria-label="Previous page"
          className={control}
        >
          <ChevronLeft className="h-4 w-4" strokeWidth={1.8} />
        </button>

        {/* Text rather than number: the spinner arrows are noise at this size, and
            inputMode still brings up a numeric keypad. */}
        <input
          type="text"
          inputMode="numeric"
          aria-label="Page number"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value.replace(/[^0-9]/g, ""))}
          onBlur={handleSubmit}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
          className="h-8 w-14 rounded border border-line bg-surface text-center text-body text-ink outline-none focus:border-action"
        />

        <button
          onClick={onNext}
          disabled={pageNumber >= numPages || numPages === 0}
          aria-label="Next page"
          className={control}
        >
          <ChevronRight className="h-4 w-4" strokeWidth={1.8} />
        </button>

        <button
          onClick={() =>
            pdfUrl && window.open(`${pdfUrl}#page=${pageNumber}`, "_blank", "noopener,noreferrer")
          }
          disabled={!pdfUrl}
          aria-label="Open in a new tab"
          title="Open in a new tab"
          className={`${control} ml-1`}
        >
          <ExternalLink className="h-4 w-4" strokeWidth={1.7} />
        </button>
      </div>
    </div>
  );
}
