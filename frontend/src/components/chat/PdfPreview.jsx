import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const MAX_PAGES = 100;

export default function PdfPreview({ data }) {
  const container = useRef(null);
  const [width, setWidth] = useState(0);
  const [status, setStatus] = useState("Loading PDF…");

  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!data || !width || !container.current) return;
    let cancelled = false;
    let task;
    let renderTask;
    const root = container.current;
    root.replaceChildren();
    setStatus("Rendering PDF…");

    (async () => {
      try {
        if (cancelled) return;
        task = pdfjs.getDocument({ data: data.slice() });
        const pdf = await task.promise;
        const count = Math.min(pdf.numPages, MAX_PAGES);
        for (let pageNumber = 1; pageNumber <= count && !cancelled; pageNumber++) {
          const page = await pdf.getPage(pageNumber);
          const initial = page.getViewport({ scale: 1 });
          const scale = Math.min(2, Math.max(0.1, (width - 8) / initial.width));
          const viewport = page.getViewport({ scale });
          const canvas = document.createElement("canvas");
          canvas.width = Math.ceil(viewport.width);
          canvas.height = Math.ceil(viewport.height);
          canvas.style.maxWidth = "100%";
          canvas.style.height = "auto";
          canvas.style.display = "block";
          canvas.style.margin = "0 auto 12px";
          canvas.style.background = "white";
          root.appendChild(canvas);
          renderTask = page.render({ canvasContext: canvas.getContext("2d"), viewport });
          await renderTask.promise;
          renderTask = null;
          page.cleanup();
        }
        if (!cancelled) setStatus(pdf.numPages > MAX_PAGES
          ? `Showing the first ${MAX_PAGES} pages. Download the original to view the rest.` : "");
      } catch (error) {
        if (!cancelled) {
          console.error("PDF preview failed:", error);
          setStatus("PDF preview unavailable. You can download the original above.");
        }
      }
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
      task?.destroy();
      root.replaceChildren();
    };
  }, [data, width]);

  return <div className="w-full min-h-full" aria-label="PDF preview">
    {status && <p className="mb-2 text-sm text-neutral-300" role="status">{status}</p>}
    <div ref={container} className="w-full" />
  </div>;
}
