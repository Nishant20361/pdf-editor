"use client";

import React, { PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  detectText, getPreviewUrl, getPreviewWithEditsUrl,
  createEdit, listEdits, undoEdits, redoEdits, resetPage as apiResetPage, resetDocument as apiResetDocument,
} from "@/lib/api";
import type {
  BackgroundCleanupMethod, DetectionResponse, DocumentMetadata,
  EditRecord, NormalizedBoundingBox, TextDetection,
} from "@/types";
import ReplacementPanel from "./ReplacementPanel";
import ExportPanel from "./ExportPanel";

interface EditorWorkspaceProps {
  document: DocumentMetadata;
  onBack?: () => void;
}

function makeManualDetection(documentId: string, pageNumber: number, box: NormalizedBoundingBox): TextDetection {
  return {
    id: `manual-${crypto.randomUUID()}`,
    document_id: documentId,
    page_number: pageNumber,
    text: "Manual selection",
    bounding_box: box,
    confidence: 1,
    source: "manual",
    font: { family: null, size: null, color: null, bold: false, italic: false },
    rotation: 0,
  };
}

export default function EditorWorkspace({ document, onBack }: EditorWorkspaceProps) {
  // ---- Page & zoom ----
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(1);

  // ---- Auto-save state ----
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");

  // ---- Detection ----
  const [query, setQuery] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [exactMatch, setExactMatch] = useState(false);
  const [result, setResult] = useState<DetectionResponse | null>(null);
  const [manual, setManual] = useState<TextDetection[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- Manual drawing ----
  const [drawing, setDrawing] = useState<{ x: number; y: number } | null>(null);
  const [draftBox, setDraftBox] = useState<NormalizedBoundingBox | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  // ---- Replacement ----
  const [replacementText, setReplacementText] = useState("");
  const [fontFamily, setFontFamily] = useState("Arial");
  const [fontSize, setFontSize] = useState(14);
  const [fontColor, setFontColor] = useState("#000000");
  const [fontWeight, setFontWeight] = useState("normal");
  const [fontStyle, setFontStyle] = useState("normal");
  const [matchOriginal, setMatchOriginal] = useState(true);
  const [alignment, setAlignment] = useState("left");
  const [letterSpacing, setLetterSpacing] = useState(0);
  const [lineHeight, setLineHeight] = useState(1.2);
  const [bgCleanup, setBgCleanup] = useState<BackgroundCleanupMethod>("solid");
  const [bgColor, setBgColor] = useState("#ffffff");

  // ---- Edits & preview ----
  const [edits, setEdits] = useState<EditRecord[]>([]);
  const [applying, setApplying] = useState(false);
  const [showEdited, setShowEdited] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [showExport, setShowExport] = useState(false);

  // ---- Editor mode ----
  const [mode, setMode] = useState<"detect" | "replace">("detect");

  const allDetections = useMemo(
    () => [...(result?.detections ?? []), ...manual],
    [result, manual],
  );
  const pageDetections = useMemo(
    () => allDetections.filter((d) => d.page_number === page),
    [allDetections, page],
  );
  const pageEdits = useMemo(
    () => edits.filter((e) => e.page_number === page),
    [edits, page],
  );

  // Sync font settings when first detection is selected
  useEffect(() => {
    if (selected.size === 0) return;
    const first = allDetections.find((d) => selected.has(d.id));
    if (!first) return;
    if (first.font.family) setFontFamily(first.font.family);
    if (first.font.size) setFontSize(first.font.size);
    if (first.font.color) setFontColor(first.font.color);
    setFontWeight(first.font.bold ? "bold" : "normal");
    setFontStyle(first.font.italic ? "italic" : "normal");
  }, [selected, allDetections]);

  const refreshEdits = useCallback(async () => {
    try {
      const resp = await listEdits(document.id);
      setEdits(resp.edits);
    } catch { /* ignore */ }
  }, [document.id]);

  useEffect(() => { void refreshEdits(); }, [refreshEdits]);

  // ---- Search ----
  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await detectText(document.id, query.trim(), undefined, caseSensitive, exactMatch);
      setResult(response);
      setSelected(new Set(response.detections.map((d) => d.id)));
      if (response.detections[0]) setPage(response.detections[0].page_number);
      if (response.detections.length > 0) setMode("replace");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Detection failed");
    } finally {
      setLoading(false);
    }
  };

  // ---- Manual drawing ----
  const point = (event: PointerEvent<HTMLDivElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.shiftKey) return;
    const start = point(event);
    if (!start) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrawing(start);
    setDraftBox({ x: start.x, y: start.y, width: 0.000001, height: 0.000001 });
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drawing) return;
    const current = point(event);
    if (!current) return;
    setDraftBox({
      x: Math.min(drawing.x, current.x),
      y: Math.min(drawing.y, current.y),
      width: Math.max(0.000001, Math.abs(current.x - drawing.x)),
      height: Math.max(0.000001, Math.abs(current.y - drawing.y)),
    });
  };

  const handlePointerUp = () => {
    if (draftBox && draftBox.width > 0.01 && draftBox.height > 0.01) {
      const item = makeManualDetection(document.id, page, draftBox);
      setManual((items) => [...items, item]);
      setSelected((items) => new Set(items).add(item.id));
    }
    setDrawing(null);
    setDraftBox(null);
  };

  const toggleSelected = (id: string) => {
    setSelected((items) => {
      const next = new Set(items);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // ---- Apply replacements ----
  const applyToDetections = async (detections: TextDetection[]) => {
    if (!replacementText.trim()) return;
    setApplying(true);
    setSaveState("saving");
    try {
      for (const det of detections) {
        await createEdit(document.id, {
          page_number: det.page_number,
          original_text: det.text,
          replacement_text: replacementText.trim(),
          original_box: det.bounding_box,
          detection_source: det.source,
          ocr_confidence: det.confidence,
          font_family: matchOriginal ? (det.font.family || fontFamily) : fontFamily,
          font_size: matchOriginal ? (det.font.size || fontSize) : fontSize,
          font_color: matchOriginal ? (det.font.color || fontColor) : fontColor,
          font_weight: matchOriginal ? (det.font.bold ? "bold" : "normal") : fontWeight,
          font_style: matchOriginal ? (det.font.italic ? "italic" : "normal") : fontStyle,
          rotation: det.rotation,
          alignment,
          letter_spacing: letterSpacing,
          line_height: lineHeight,
          bg_cleanup: bgCleanup,
          bg_color: bgCleanup === "manual_color" ? bgColor : undefined,
        });
      }
      await refreshEdits();
      setPreviewKey((k) => k + 1);
      setShowEdited(true);
      setSaveState("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply edit");
      setSaveState("error");
    } finally {
      setApplying(false);
    }
  };

  const handleApplySelected = () => {
    const targets = allDetections.filter((d) => selected.has(d.id));
    void applyToDetections(targets);
  };

  const handleApplyAll = () => void applyToDetections(allDetections);

  const handleUndo = async () => {
    setSaveState("saving");
    try {
      const resp = await undoEdits(document.id);
      setEdits(resp.edits);
      setPreviewKey((k) => k + 1);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  const handleRedo = async () => {
    setSaveState("saving");
    try {
      const resp = await redoEdits(document.id);
      setEdits(resp.edits);
      setPreviewKey((k) => k + 1);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  const handleResetPage = async () => {
    setSaveState("saving");
    try {
      await apiResetPage(document.id, page);
      await refreshEdits();
      setPreviewKey((k) => k + 1);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  const handleResetDocument = async () => {
    setSaveState("saving");
    try {
      await apiResetDocument(document.id);
      await refreshEdits();
      setPreviewKey((k) => k + 1);
      setShowEdited(false);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  // ---- Preview URLs ----
  const originalUrl = getPreviewUrl(document.id, page);
  const editedUrl = `${getPreviewWithEditsUrl(document.id, page)}&_k=${previewKey}`;
  const previewUrl = showEdited && pageEdits.length > 0 ? editedUrl : originalUrl;
  const pageType = result?.pages.find((p) => p.page_number === page)?.content_type;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px] animate-slide-up">
      {/* Left: Preview */}
      <section className="glass-card overflow-hidden rounded-2xl">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-3">
            {onBack && (
              <button
                onClick={onBack}
                className="p-1.5 rounded-lg border border-border hover:bg-surface-hover text-muted hover:text-white transition-colors"
                title="Back to Dashboard"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </button>
            )}
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold">{document.original_filename}</p>
                {saveState === "saving" && (
                  <span className="flex items-center gap-1 text-[11px] text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded-full border border-sky-500/20">
                    <svg className="w-2.5 h-2.5 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Saving...
                  </span>
                )}
                {saveState === "saved" && edits.length > 0 && (
                  <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Saved
                  </span>
                )}
                {saveState === "error" && (
                  <span className="text-[11px] text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20">
                    Save error
                  </span>
                )}
              </div>
              <p className="text-xs text-muted">Shift+drag to draw a manual selection</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pageType && (
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold capitalize text-primary">
                {pageType}
              </span>
            )}
            {/* Before/After toggle */}
            {edits.length > 0 && (
              <button
                onClick={() => setShowEdited(!showEdited)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${showEdited ? "border-success bg-success/10 text-success" : "border-border hover:bg-surface-hover"}`}
              >
                {showEdited ? "✓ Edited" : "Original"}
              </button>
            )}
            {/* Zoom */}
            <div className="flex items-center gap-1 rounded-lg border border-border">
              <button
                className="px-2 py-1.5 text-xs font-bold hover:bg-surface-hover rounded-l-lg"
                onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
              >−</button>
              <span className="text-xs tabular-nums w-12 text-center">{Math.round(zoom * 100)}%</span>
              <button
                className="px-2 py-1.5 text-xs font-bold hover:bg-surface-hover rounded-r-lg"
                onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
              >+</button>
            </div>
            {/* Page nav */}
            {document.page_count > 1 && (
              <>
                <button className="editor-button" disabled={page === 0} onClick={() => setPage((v) => v - 1)}>Prev</button>
                <span className="text-sm tabular-nums text-muted">{page + 1} / {document.page_count}</span>
                <button className="editor-button" disabled={page === document.page_count - 1} onClick={() => setPage((v) => v + 1)}>Next</button>
              </>
            )}
            {/* Export button */}
            <button
              onClick={() => setShowExport(true)}
              disabled={edits.length === 0}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-30 hover:bg-primary-hover transition-colors"
            >
              ⬇ Export
            </button>
          </div>
        </div>

        {/* Preview canvas */}
        <div className="bg-[#111522] p-4 md:p-6 overflow-auto">
          <div
            ref={canvasRef}
            className="relative mx-auto w-fit max-w-full touch-none select-none"
            style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt={`Page ${page + 1}`}
              className="block max-h-[72vh] max-w-full object-contain shadow-2xl"
              draggable={false}
            />
            {/* Detection boxes */}
            {!showEdited && pageDetections.map((item) => {
              const box = item.bounding_box;
              const active = selected.has(item.id);
              return (
                <button
                  type="button"
                  key={item.id}
                  title={`${item.text} · ${Math.round(item.confidence * 100)}%`}
                  onClick={(e) => { e.stopPropagation(); toggleSelected(item.id); }}
                  className={`absolute border-2 transition-colors ${active ? "border-primary bg-primary/20" : "border-warning bg-warning/10"}`}
                  style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }}
                />
              );
            })}
            {/* Edit boxes shown on edited preview */}
            {showEdited && pageEdits.map((edit) => {
              const box = edit.current_box;
              return (
                <div
                  key={edit.id}
                  className="absolute border border-dashed border-success/50"
                  style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }}
                />
              );
            })}
            {/* Draft drawing */}
            {draftBox && (
              <div
                className="absolute border-2 border-dashed border-success bg-success/15"
                style={{ left: `${draftBox.x * 100}%`, top: `${draftBox.y * 100}%`, width: `${draftBox.width * 100}%`, height: `${draftBox.height * 100}%` }}
              />
            )}
          </div>
        </div>
      </section>

      {/* Right: Side panel */}
      <aside className="glass-card rounded-2xl p-5 lg:sticky lg:top-24 lg:self-start overflow-y-auto max-h-[calc(100vh-120px)]">
        {/* Mode tabs */}
        <div className="flex gap-1 mb-5 rounded-xl border border-border p-1">
          <button
            onClick={() => setMode("detect")}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${mode === "detect" ? "bg-primary text-white" : "hover:bg-surface-hover"}`}
          >
            🔍 Find
          </button>
          <button
            onClick={() => setMode("replace")}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${mode === "replace" ? "bg-primary text-white" : "hover:bg-surface-hover"}`}
          >
            ✏️ Replace
          </button>
        </div>

        {/* DETECT mode */}
        {mode === "detect" && (
          <div>
            <div className="mb-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Phase 2</p>
              <h2 className="mt-1 text-xl font-bold">Find text</h2>
              <p className="mt-1 text-sm text-muted">Search native PDF text and OCR-readable image text.</p>
            </div>
            <label className="block text-sm font-medium" htmlFor="text-query">Text to find</label>
            <div className="mt-2 flex gap-2">
              <input
                id="text-query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void search(); }}
                placeholder="e.g. Shrabani"
                className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-primary"
              />
              <button
                onClick={() => void search()}
                disabled={loading || !query.trim()}
                className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
              >
                {loading ? "Scanning…" : "Find"}
              </button>
            </div>
            <div className="mt-4 grid gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} /> Case sensitive
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={exactMatch} onChange={(e) => setExactMatch(e.target.checked)} /> Exact match
              </label>
            </div>
            {error && <p className="mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
            {result?.warnings.map((w) => (
              <p key={w} className="mt-4 rounded-xl bg-warning/10 p-3 text-sm text-warning">{w}</p>
            ))}

            {/* Occurrences list */}
            <div className="mt-6 flex items-center justify-between border-t border-border pt-4">
              <div>
                <p className="text-sm font-semibold">Occurrences</p>
                <p className="text-xs text-muted">{allDetections.length} found · {selected.size} selected</p>
              </div>
              <button
                className="text-sm font-semibold text-primary"
                onClick={() => setSelected(new Set(allDetections.map((d) => d.id)))}
              >
                Select all
              </button>
            </div>
            <div className="mt-3 max-h-[35vh] space-y-2 overflow-auto pr-1">
              {allDetections.map((item) => (
                <button
                  key={item.id}
                  onClick={() => { setPage(item.page_number); toggleSelected(item.id); }}
                  className={`w-full rounded-xl border p-3 text-left transition-colors ${selected.has(item.id) ? "border-primary bg-primary/10" : "border-border hover:bg-surface-hover"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="truncate text-sm font-semibold">{item.text}</p>
                    <input type="checkbox" readOnly checked={selected.has(item.id)} className="mt-0.5" />
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    Page {item.page_number + 1} · {item.source.replace("_", " ")} · {Math.round(item.confidence * 100)}%
                  </p>
                  {item.font.family && (
                    <p className="mt-1 truncate text-xs text-muted">{item.font.family} · {item.font.size?.toFixed(1)} pt</p>
                  )}
                </button>
              ))}
              {result && allDetections.length === 0 && (
                <p className="rounded-xl border border-dashed border-border p-4 text-center text-sm text-muted">
                  No matching text found. Try partial matching or draw a manual selection.
                </p>
              )}
            </div>

            {/* Quick replace button */}
            {allDetections.length > 0 && (
              <button
                onClick={() => setMode("replace")}
                className="mt-4 w-full rounded-xl bg-primary/10 border border-primary/20 px-4 py-3 text-sm font-semibold text-primary hover:bg-primary/20 transition-colors"
              >
                → Replace {selected.size} selected occurrence{selected.size !== 1 ? "s" : ""}
              </button>
            )}
          </div>
        )}

        {/* REPLACE mode */}
        {mode === "replace" && (
          <ReplacementPanel
            replacementText={replacementText}
            onReplacementTextChange={setReplacementText}
            fontFamily={fontFamily}
            onFontFamilyChange={setFontFamily}
            fontSize={fontSize}
            onFontSizeChange={setFontSize}
            fontColor={fontColor}
            onFontColorChange={setFontColor}
            fontWeight={fontWeight}
            onFontWeightChange={setFontWeight}
            fontStyle={fontStyle}
            onFontStyleChange={setFontStyle}
            matchOriginal={matchOriginal}
            onMatchOriginalChange={setMatchOriginal}
            alignment={alignment}
            onAlignmentChange={setAlignment}
            letterSpacing={letterSpacing}
            onLetterSpacingChange={setLetterSpacing}
            lineHeight={lineHeight}
            onLineHeightChange={setLineHeight}
            bgCleanup={bgCleanup}
            onBgCleanupChange={setBgCleanup}
            bgColor={bgColor}
            onBgColorChange={setBgColor}
            selectedCount={selected.size}
            totalCount={allDetections.length}
            onApplySelected={handleApplySelected}
            onApplyAll={handleApplyAll}
            onUndo={handleUndo}
            onRedo={handleRedo}
            onResetPage={handleResetPage}
            onResetDocument={handleResetDocument}
            applying={applying}
            editCount={edits.length}
          />
        )}
      </aside>

      {/* Export modal */}
      {showExport && (
        <ExportPanel
          document={document}
          currentPage={page}
          editCount={edits.length}
          onClose={() => setShowExport(false)}
        />
      )}
    </div>
  );
}
