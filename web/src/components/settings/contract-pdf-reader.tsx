"use client";

import { useEffect, useRef, useState } from "react";

type ReaderLabels = {
  loading: string;
  failed: string;
  page: string;
  of: string;
  zoomIn: string;
  zoomOut: string;
};

export function ContractPdfReader({ data, labels }: { data: ArrayBuffer; labels: ReaderLabels }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.15);
  const [error, setError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const host = hostRef.current;

    async function renderPages() {
      setRendering(true);
      setError(null);
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const task = pdfjs.getDocument({ data: data.slice(0) });
        const pdf = await task.promise;
        if (cancelled || !host) return;
        setPageCount(pdf.numPages);
        host.replaceChildren();
        for (let index = 1; index <= pdf.numPages; index += 1) {
          const pdfPage = await pdf.getPage(index);
          const viewport = pdfPage.getViewport({ scale });
          const canvas = document.createElement("canvas");
          const context = canvas.getContext("2d");
          if (!context) continue;
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.className = "mx-auto mb-4 block bg-white shadow-md";
          canvas.style.width = `${Math.floor(viewport.width)}px`;
          canvas.style.maxWidth = "100%";
          canvas.setAttribute("data-page", String(index));
          host.appendChild(canvas);
          await pdfPage.render({ canvasContext: context, viewport }).promise;
          if (cancelled) return;
        }
      } catch {
        if (!cancelled) setError(labels.failed);
      } finally {
        if (!cancelled) setRendering(false);
      }
    }

    void renderPages();
    return () => {
      cancelled = true;
    };
  }, [data, labels.failed, scale]);

  const showPage = (next: number) => {
    const target = Math.min(Math.max(next, 1), Math.max(pageCount, 1));
    setPage(target);
    hostRef.current?.querySelector(`[data-page="${target}"]`)?.scrollIntoView({ block: "start" });
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
          {labels.page} {page} {labels.of} {pageCount || "—"}
        </p>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => showPage(page - 1)} className="h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-800 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-100">
            ‹
          </button>
          <button type="button" onClick={() => showPage(page + 1)} className="h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-800 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-100">
            ›
          </button>
          <button type="button" onClick={() => setScale((value) => Math.max(0.8, Number((value - 0.15).toFixed(2))))} className="h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-800 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-100">
            {labels.zoomOut}
          </button>
          <button type="button" onClick={() => setScale((value) => Math.min(2, Number((value + 0.15).toFixed(2))))} className="h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-800 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-100">
            {labels.zoomIn}
          </button>
        </div>
      </div>
      <div className="max-h-[70vh] overflow-auto rounded-xl bg-slate-200 p-4 dark:bg-slate-800">
        {rendering && <p className="mb-2 text-xs text-slate-600">{labels.loading}</p>}
        {error && <p className="mb-2 text-xs text-amber-800">{error}</p>}
        <div ref={hostRef} />
      </div>
    </div>
  );
}
