"use client";

import React, { useCallback, useEffect, useState } from "react";
import { createExport, getExportDownloadUrl, getExportStatus } from "@/lib/api";
import { formatFileSize } from "@/types";
import type { DocumentMetadata, ExportFormat, ExportJob, PageSelection } from "@/types";

interface ExportPanelProps {
  document: DocumentMetadata;
  currentPage: number;
  editCount: number;
  onClose: () => void;
}

const FORMAT_OPTIONS: { value: ExportFormat; label: string; desc: string }[] = [
  { value: "pdf", label: "PDF (Preserve)", desc: "Vector content preserved" },
  { value: "pdf_flattened", label: "PDF (Flattened)", desc: "All pages rendered as images" },
  { value: "png", label: "PNG", desc: "Lossless image" },
  { value: "jpeg", label: "JPEG", desc: "Compressed image" },
  { value: "webp", label: "WebP", desc: "Modern compressed image" },
  { value: "zip_images", label: "ZIP (Page Images)", desc: "All pages as separate images" },
];

const PAGE_OPTIONS: { value: PageSelection; label: string }[] = [
  { value: "all", label: "All Pages" },
  { value: "current", label: "Current Page" },
  { value: "edited", label: "Edited Pages Only" },
  { value: "custom", label: "Custom Range" },
];

export default function ExportPanel({ document, currentPage, editCount, onClose }: ExportPanelProps) {
  const isPdf = document.document_type === "pdf";

  const [format, setFormat] = useState<ExportFormat>(isPdf ? "pdf" : "png");
  const [pageSelection, setPageSelection] = useState<PageSelection>("all");
  const [customPages, setCustomPages] = useState("");
  const [filename, setFilename] = useState("");
  const [quality, setQuality] = useState(85);
  const [preserveDimensions, setPreserveDimensions] = useState(true);
  const [zipImageFormat, setZipImageFormat] = useState<"png" | "jpeg">("png");

  const [job, setJob] = useState<ExportJob | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isImageFormat = format === "png" || format === "jpeg" || format === "webp";
  const showQuality = format === "jpeg" || format === "webp" || format === "pdf_flattened";
  const showPageSelection = isPdf && !isImageFormat;

  // Poll export status
  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed" || job.status === "cancelled") return;
    const interval = setInterval(async () => {
      try {
        const updated = await getExportStatus(document.id, job.id);
        setJob(updated);
        if (updated.status === "completed" || updated.status === "failed") {
          setExporting(false);
        }
      } catch { /* ignore polling errors */ }
    }, 1000);
    return () => clearInterval(interval);
  }, [job, document.id]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setError(null);
    setJob(null);
    try {
      const result = await createExport(document.id, {
        output_format: format,
        mode: format === "pdf_flattened" ? "flattened" : "preserve",
        page_selection: showPageSelection ? pageSelection : "all",
        current_page: currentPage,
        custom_pages: pageSelection === "custom" ? customPages : undefined,
        filename: filename.trim() || undefined,
        quality,
        preserve_dimensions: preserveDimensions,
        image_format_for_zip: zipImageFormat,
      });
      setJob(result);
      if (result.status === "completed" || result.status === "failed") {
        setExporting(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
      setExporting(false);
    }
  }, [document.id, format, pageSelection, currentPage, customPages, filename, quality, preserveDimensions, zipImageFormat, showPageSelection]);

  const handleDownload = useCallback(() => {
    if (!job) return;
    const url = getExportDownloadUrl(document.id, job.id);
    const a = window.document.createElement("a");
    a.href = url;
    a.download = job.filename;
    window.document.body.appendChild(a);
    a.click();
    window.document.body.removeChild(a);
  }, [job, document.id]);

  const handleExportAgain = () => {
    setJob(null);
    setError(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="glass-card w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Phase 4</p>
            <h2 className="text-xl font-bold mt-1">Export Document</h2>
            <p className="text-sm text-muted mt-0.5">{editCount} edit{editCount !== 1 ? "s" : ""} to apply</p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-foreground text-2xl leading-none" aria-label="Close">×</button>
        </div>

        {/* Completed state */}
        {job?.status === "completed" && (
          <div className="space-y-4">
            <div className="rounded-xl bg-success/10 border border-success/20 p-4">
              <p className="text-sm font-semibold text-success">✓ Export complete</p>
              <div className="mt-3 space-y-1 text-sm">
                <p><span className="text-muted">Filename:</span> {job.filename}</p>
                <p><span className="text-muted">Format:</span> {job.output_format.toUpperCase()}</p>
                <p><span className="text-muted">Pages:</span> {job.page_count}</p>
                <p><span className="text-muted">Size:</span> {formatFileSize(job.file_size)}</p>
              </div>
            </div>
            <button
              onClick={handleDownload}
              className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white hover:bg-primary-hover transition-colors"
            >
              ⬇ Download {job.filename}
            </button>
            <button
              onClick={handleExportAgain}
              className="w-full rounded-xl border border-border px-4 py-2.5 text-sm font-semibold hover:bg-surface-hover transition-colors"
            >
              Export Again with Different Settings
            </button>
          </div>
        )}

        {/* Failed state */}
        {job?.status === "failed" && (
          <div className="space-y-4">
            <div className="rounded-xl bg-danger/10 border border-danger/20 p-4">
              <p className="text-sm font-semibold text-danger">Export failed</p>
              <p className="text-sm text-muted mt-1">{job.error || "Unknown error"}</p>
            </div>
            <button onClick={handleExportAgain} className="w-full rounded-xl border border-border px-4 py-2.5 text-sm font-semibold hover:bg-surface-hover">
              Try Again
            </button>
          </div>
        )}

        {/* Processing state */}
        {exporting && job?.status === "processing" && (
          <div className="space-y-4">
            <p className="text-sm font-semibold">Exporting…</p>
            <div className="w-full bg-border rounded-full h-2">
              <div className="bg-primary h-2 rounded-full transition-all duration-300" style={{ width: `${job.progress}%` }} />
            </div>
            <p className="text-xs text-muted text-center">{Math.round(job.progress)}%</p>
          </div>
        )}

        {/* Settings form — shown when no job or ready to re-export */}
        {!job && !exporting && (
          <div className="space-y-5">
            {/* Filename */}
            <div>
              <label className="block text-sm font-medium mb-1.5">Output Filename</label>
              <input
                type="text"
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder={`${document.original_filename.replace(/\.[^.]+$/, "")}_edited`}
                className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-primary"
              />
            </div>

            {/* Format */}
            <div>
              <label className="block text-sm font-medium mb-1.5">Output Format</label>
              <div className="grid grid-cols-2 gap-2">
                {FORMAT_OPTIONS.filter((f) => isPdf || f.value === "png" || f.value === "jpeg" || f.value === "webp").map((f) => (
                  <button
                    key={f.value}
                    onClick={() => setFormat(f.value)}
                    className={`rounded-xl border p-3 text-left transition-colors ${format === f.value ? "border-primary bg-primary/10" : "border-border hover:bg-surface-hover"}`}
                  >
                    <p className="text-sm font-semibold">{f.label}</p>
                    <p className="text-xs text-muted mt-0.5">{f.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Quality slider */}
            {showQuality && (
              <div>
                <label className="block text-sm font-medium mb-1.5">Quality: {quality}%</label>
                <input
                  type="range"
                  min={1} max={100} value={quality}
                  onChange={(e) => setQuality(Number(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted">
                  <span>Smaller file</span>
                  <span>Best quality</span>
                </div>
              </div>
            )}

            {/* Page selection */}
            {showPageSelection && (
              <div>
                <label className="block text-sm font-medium mb-1.5">Pages</label>
                <div className="grid grid-cols-2 gap-2">
                  {PAGE_OPTIONS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => setPageSelection(p.value)}
                      className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${pageSelection === p.value ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-hover"}`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {pageSelection === "custom" && (
                  <input
                    type="text"
                    value={customPages}
                    onChange={(e) => setCustomPages(e.target.value)}
                    placeholder="e.g. 1-3,5,8-10"
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
                  />
                )}
              </div>
            )}

            {/* ZIP image format */}
            {format === "zip_images" && (
              <div>
                <label className="block text-sm font-medium mb-1.5">Image Format in ZIP</label>
                <div className="flex gap-2">
                  {(["png", "jpeg"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setZipImageFormat(f)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium uppercase transition-colors ${zipImageFormat === f ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-hover"}`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Preserve dimensions */}
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={preserveDimensions} onChange={(e) => setPreserveDimensions(e.target.checked)} className="accent-primary w-4 h-4" />
              <span className="text-sm">Preserve original dimensions</span>
            </label>

            {error && <p className="rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

            {/* Export button */}
            <button
              onClick={handleExport}
              disabled={exporting}
              className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white disabled:opacity-40 hover:bg-primary-hover transition-colors"
            >
              {exporting ? "Exporting…" : "Export"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
