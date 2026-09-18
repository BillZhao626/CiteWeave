import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileText } from "lucide-react";
import type { Citation } from "./api";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export function PdfEvidence({ citation }: { citation: Citation }) {
  const initial = citation.span.boxes[0].page_index;
  const [pageIndex, setPageIndex] = useState(initial),
    [pages, setPages] = useState(0),
    [error, setError] = useState("");
  const [ready, setReady] = useState(false),
    [size, setSize] = useState({ width: 500, height: 707 });
  const canvas = useRef<HTMLCanvasElement>(null),
    anchor = useRef<HTMLDivElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const [renderWidth, setRenderWidth] = useState(240);
  useEffect(() => {
    if (!scroll.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setRenderWidth(
        Math.min(520, Math.max(160, Math.floor(entry.contentRect.width))),
      );
    });
    observer.observe(scroll.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let stopped = false,
      cleanup = () => {};
    const abort = new AbortController();
    setReady(false);
    setError("");
    void (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
      const response = await fetch(citation.content_url, {
        signal: abort.signal,
      });
      if (!response.ok) throw new Error("无法读取授权文档");
      const task = pdfjs.getDocument({
        data: new Uint8Array(await response.arrayBuffer()),
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/",
        wasmUrl: "/pdfjs/wasm/",
      });
      cleanup = () => {
        void task.destroy();
      };
      const pdf = await task.promise;
      if (stopped) return cleanup();
      setPages(pdf.numPages);
      const page = await pdf.getPage(pageIndex + 1);
      const viewport = page.getViewport({ scale: 1 });
      // Evidence boxes use the same post-rotation display page, normalized independently of zoom.
      const scale = renderWidth / viewport.width,
        display = page.getViewport({ scale }),
        dpr = window.devicePixelRatio || 1;
      const element = canvas.current;
      if (!element || stopped) return;
      element.width = display.width * dpr;
      element.height = display.height * dpr;
      setSize({ width: display.width, height: display.height });
      await page.render({
        canvas: element,
        viewport: display,
        transform: [dpr, 0, 0, dpr, 0, 0],
      }).promise;
      if (!stopped) {
        setReady(true);
        requestAnimationFrame(() =>
          anchor.current?.scrollIntoView({
            behavior: "smooth",
            block: "center",
          }),
        );
      }
    })().catch((e) => {
      if (!stopped) setError(e instanceof Error ? e.message : "PDF 显示失败");
    });
    return () => {
      stopped = true;
      abort.abort();
      cleanup();
    };
  }, [citation.content_url, pageIndex, renderWidth]);
  const boxes = citation.span.boxes.filter(
    (box) => box.page_index === pageIndex,
  );
  return (
    <div className="pdf-viewer">
      <div className="source-meta">
        <FileText size={16} />
        <strong>{citation.filename}</strong>
      </div>
      <p className="version-meta">
        固定版本 {citation.document_version_id.slice(0, 8)} · 原始 PDF
      </p>
      <blockquote>{citation.span.quote}</blockquote>
      <div className="pdf-toolbar">
        <button
          aria-label="上一页"
          disabled={pageIndex === 0}
          onClick={() => setPageIndex((p) => p - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <span>
          第 <strong>{pageIndex + 1}</strong> / {pages || "…"} 页
        </span>
        <button
          aria-label="下一页"
          disabled={!pages || pageIndex + 1 >= pages}
          onClick={() => setPageIndex((p) => p + 1)}
        >
          <ChevronRight size={16} />
        </button>
        <button className="text-button" onClick={() => setPageIndex(initial)}>
          返回引用页
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="pdf-scroll" ref={scroll}>
        <div
          className="pdf-page"
          style={{ width: size.width, height: size.height }}
          data-page-index={pageIndex}
        >
          <canvas
            ref={canvas}
            aria-label={`原始 PDF 第 ${pageIndex + 1} 页`}
            style={{ width: size.width, height: size.height }}
          />
          {ready &&
            boxes.map((box, i) => (
              <div
                key={i}
                ref={i === 0 ? anchor : undefined}
                className="evidence-highlight"
                data-evidence-id={citation.evidence_id}
                style={{
                  left: box.left * size.width,
                  top: box.top * size.height,
                  width: (box.right - box.left) * size.width,
                  height: (box.bottom - box.top) * size.height,
                }}
              />
            ))}
        </div>
      </div>
      <small className="evidence-note">
        高亮标记对应原文字符范围。文档和答案均绑定具体版本。
      </small>
    </div>
  );
}
