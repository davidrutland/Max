import { lazy, Suspense, useEffect, useRef, useState } from "react";

const PdfPreview = lazy(() => import("./PdfPreview.jsx"));

const textFile = (name) => /\.(txt|md|markdown|json|csv|log|xml|css|js|jsx|ts|tsx|py|sh|yaml|yml|toml|ini|sql|html|htm)$/i.test(name);
const htmlFile = (name) => /\.(html|htm|zip)$/i.test(name);
const imageFile = (name) => /\.(png|jpe?g|gif|webp|bmp|avif|svg)$/i.test(name);
const mediaFile = (name) => /\.(mp3|wav|ogg|m4a|mp4|webm)$/i.test(name);

export default function ArtifactPreview({ artifact, onClose }) {
  const [view, setView] = useState({ loading: true });
  const previewArea = useRef(null);
  const [previewSize, setPreviewSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!view.previewUrl || !previewArea.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setPreviewSize({ width, height });
    });
    observer.observe(previewArea.current);
    return () => observer.disconnect();
  }, [view.previewUrl]);
  // Opaque-origin iframes cannot be measured internally. Use a conservative
  // desktop canvas on narrow screens, scaled to fit without altering its code.
  const designWidth = 960;
  const scale = previewSize.width > 0 && previewSize.width < 768
    ? previewSize.width / designWidth : 1;
  useEffect(() => {
    if (!artifact) return;
    const controller = new AbortController();
    let url;
    setView({ loading: true });
    (async () => {
      try {
        if (htmlFile(artifact.filename)) {
          const ticketResponse = await fetch(`/api/artifacts/${encodeURIComponent(artifact.id)}/preview-ticket`, { method: "POST", signal: controller.signal });
          if (!ticketResponse.ok) throw new Error(`Preview unavailable (${ticketResponse.status})`);
          const { ticket } = await ticketResponse.json();
          if (!controller.signal.aborted) setView({ previewUrl: `/preview/${encodeURIComponent(ticket)}` });
          return;
        }
        const response = await fetch(`/api/artifacts/${encodeURIComponent(artifact.id)}/download`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Download failed (${response.status})`);
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (/\.pdf$/i.test(artifact.filename)) {
          setView({ pdfData: new Uint8Array(await blob.arrayBuffer()) });
          return;
        }
        if (textFile(artifact.filename)) {
          setView({ text: await blob.text() });
        } else if (imageFile(artifact.filename) || mediaFile(artifact.filename) || /\.pdf$/i.test(artifact.filename)) {
          const mime = imageFile(artifact.filename) ? artifact.mime_type : /\.pdf$/i.test(artifact.filename) ? "application/pdf" : artifact.mime_type;
          url = URL.createObjectURL(new Blob([blob], { type: mime }));
          setView({ url });
        } else {
          setView({ unsupported: true });
        }
      } catch (error) {
        if (!controller.signal.aborted) setView({ error: String(error) });
      }
    })();
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [artifact]);
  useEffect(() => {
    if (!artifact) return;
    const handler = (event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [artifact, onClose]);
  if (!artifact) return null;
  const name = artifact.filename;
  return <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
    <section className="bg-neutral-900 text-neutral-100 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
      <header className="flex gap-4 items-center px-4 py-3 border-b border-neutral-700">
        <strong className="truncate flex-1">{name}</strong>
        <a href={`/api/artifacts/${encodeURIComponent(artifact.id)}/download`} className="underline">Download</a>
        <button onClick={onClose} aria-label="Close preview">✕</button>
      </header>
      <div className="flex-1 min-h-0 overflow-auto p-3">
        {view.loading && <p>Loading preview…</p>}
        {view.error && <p role="alert">{view.error}</p>}
        {view.unsupported && <p>Preview unavailable for this file type. You can download the original.</p>}
        {view.previewUrl && <div ref={previewArea} className="w-full h-full overflow-hidden bg-white">
          {previewSize.width > 0 && <iframe title="Isolated HTML preview" sandbox="allow-scripts" referrerPolicy="no-referrer"
            src={view.previewUrl} style={{ width: scale < 1 ? designWidth : "100%", height: scale < 1 ? `${previewSize.height / scale}px` : "100%",
              transform: scale < 1 ? `scale(${scale})` : undefined, transformOrigin: "top left", border: 0 }} />}
        </div>}
        {view.text !== undefined && <pre className="text-xs whitespace-pre-wrap break-words">{view.text}</pre>}
        {view.pdfData && <Suspense fallback={<p>Loading PDF viewer…</p>}><PdfPreview data={view.pdfData} /></Suspense>}
        {view.url && (imageFile(name) ? <img src={view.url} alt={name} className="max-w-full max-h-full mx-auto" /> : /\.(mp4|webm)$/i.test(name) ? <video src={view.url} controls className="max-w-full max-h-full mx-auto" /> : <audio src={view.url} controls />)}
      </div>
    </section>
  </div>;
}
