"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import PdfToolbar from "./pdf-toolbar";
import { PAGE_WINDOW } from "@/lib/config";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

const Document = dynamic(() => import("react-pdf").then((m) => m.Document), {
  ssr: false,
});
const Page = dynamic(() => import("react-pdf").then((m) => m.Page), {
  ssr: false,
});

type Props = {
  url?: string;
  title?: string;
  subtitle?: string;
  /** PDF index, not the printed number. */
  page?: number;
};

const PDF_OPTIONS = {
  cMapUrl: "/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/standard_fonts/",
};

/** Starting guess only. Replaced with the document's real ratio once page 1 loads. */
const ASSUMED_RATIO = 1.414;

/** Vertical space between pages. Rows are otherwise exactly one page tall, so
 *  that scroll offset and page number stay in step. */
const GAP = 16;

export default function PdfViewer({ url, title, subtitle, page = 1 }: Props) {
  const [numPages, setNumPages] = useState(0);
  const [current, setCurrent] = useState(1);
  const [ready, setReady] = useState(false);
  const [width, setWidth] = useState(600);
  const [ratio, setRatio] = useState(ASSUMED_RATIO);

  const frameRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const jumpingRef = useRef(false);

  useEffect(() => {
    let mounted = true;
    import("react-pdf").then((module) => {
      // Served from public/, not a CDN — everything runs locally.
      module.pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
      if (mounted) setReady(true);
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const measure = () => {
      if (frameRef.current) setWidth(Math.max(300, frameRef.current.offsetWidth - 32));
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (frameRef.current) observer.observe(frameRef.current);
    return () => observer.disconnect();
  }, []);

  /**
   * Only a window around the current page is mounted; everything else is a
   * spacer of the right height. PDF.js degrades past ~25 pages at once, and the
   * previous build mounted every page from 1 to the one you jumped to.
   */
  const window_ = useMemo(() => {
    if (!numPages) return { first: 1, last: 0 };
    const half = Math.floor(PAGE_WINDOW / 2);
    const first = Math.max(1, Math.min(current - half, numPages - PAGE_WINDOW + 1));
    return { first: Math.max(1, first), last: Math.min(numPages, first + PAGE_WINDOW - 1) };
  }, [current, numPages]);

  const pages = useMemo(() => {
    const list: number[] = [];
    for (let n = window_.first; n <= window_.last; n += 1) list.push(n);
    return list;
  }, [window_]);

  const row = width * ratio + GAP;
  const before = (window_.first - 1) * row;
  const after = numPages ? (numPages - window_.last) * row : 0;

  const jump = (target: number, smooth = true) => {
    const container = scrollRef.current;
    if (!container || !numPages) return;

    const safe = Math.max(1, Math.min(target, numPages));
    jumpingRef.current = true;
    setCurrent(safe);

    // Scroll by computed offset rather than to an element: the target page may
    // not be mounted yet on a long jump.
    container.scrollTo({
      top: (safe - 1) * row,
      behavior: smooth ? "smooth" : "auto",
    });
    window.setTimeout(() => {
      jumpingRef.current = false;
    }, 400);
  };

  // Follow the scroll position so the toolbar's page number stays honest.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !numPages) return;

    const onScroll = () => {
      if (jumpingRef.current) return;
      const index = Math.floor(container.scrollTop / row + 0.5) + 1;
      setCurrent(Math.max(1, Math.min(index, numPages)));
    };

    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, [numPages, row]);

  // A citation click arrives as a page change from outside.
  useEffect(() => {
    if (page >= 1 && numPages) jump(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, numPages]);

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <PdfToolbar
        title={title || "Manual"}
        subtitle={subtitle}
        pageNumber={current}
        numPages={numPages}
        onPrev={() => jump(current - 1)}
        onNext={() => jump(current + 1)}
        onJump={jump}
        pdfUrl={url}
      />

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto bg-slate-100 p-4">
        <div ref={frameRef} className="mx-auto flex w-full max-w-3xl flex-col items-center">
          {!url ? (
            <p className="rounded-xl bg-white px-4 py-6 text-sm text-slate-500 shadow-sm">
              Choose a manual to see its pages here.
            </p>
          ) : !ready ? (
            <p className="rounded-xl bg-white px-4 py-6 text-sm text-slate-500 shadow-sm">
              Loading viewer…
            </p>
          ) : (
            <Document
              file={url}
              options={PDF_OPTIONS}
              onLoadSuccess={({ numPages: total }) => setNumPages(total)}
              loading={
                <p className="rounded-xl bg-white px-4 py-6 text-sm text-slate-500 shadow-sm">
                  Loading manual…
                </p>
              }
              error={
                <p className="rounded-xl bg-white px-4 py-6 text-sm text-red-500 shadow-sm">
                  Could not open this manual.
                </p>
              }
              className="flex w-full flex-col items-center"
            >
              <div style={{ height: before }} aria-hidden />

              <div className="flex flex-col items-center" style={{ gap: GAP }}>
                {pages.map((n) => (
                  <Page
                    key={n}
                    pageNumber={n}
                    width={width}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    className="rounded-xl shadow-md"
                    // The spacers stand in for unmounted pages, so their height
                    // has to be the document's real one, not an assumed A4.
                    onLoadSuccess={(page) => {
                      const view = page.getViewport({ scale: 1 });
                      const actual = view.height / view.width;
                      if (Math.abs(actual - ratio) > 0.002) setRatio(actual);
                    }}
                    loading={
                      <div
                        style={{ width, height: width * ratio }}
                        className="rounded-xl bg-white shadow-sm"
                      />
                    }
                  />
                ))}
              </div>

              <div style={{ height: after }} aria-hidden />
            </Document>
          )}
        </div>
      </div>
    </section>
  );
}
