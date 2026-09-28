"use client";

import React from "react";
import type { BackgroundCleanupMethod } from "@/types";

interface ReplacementPanelProps {
  replacementText: string;
  onReplacementTextChange: (text: string) => void;
  fontFamily: string;
  onFontFamilyChange: (font: string) => void;
  fontSize: number;
  onFontSizeChange: (size: number) => void;
  fontColor: string;
  onFontColorChange: (color: string) => void;
  fontWeight: string;
  onFontWeightChange: (weight: string) => void;
  fontStyle: string;
  onFontStyleChange: (style: string) => void;
  matchOriginal: boolean;
  onMatchOriginalChange: (match: boolean) => void;
  alignment: string;
  onAlignmentChange: (align: string) => void;
  letterSpacing: number;
  onLetterSpacingChange: (spacing: number) => void;
  lineHeight: number;
  onLineHeightChange: (lh: number) => void;
  bgCleanup: BackgroundCleanupMethod;
  onBgCleanupChange: (method: BackgroundCleanupMethod) => void;
  bgColor: string;
  onBgColorChange: (color: string) => void;
  selectedCount: number;
  totalCount: number;
  onApplySelected: () => void;
  onApplyAll: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onResetPage: () => void;
  onResetDocument: () => void;
  applying: boolean;
  editCount: number;
}

const FONTS = ["Arial", "Helvetica", "Times New Roman", "Courier New", "Georgia", "Verdana", "Impact"];
const CLEANUP_METHODS: { value: BackgroundCleanupMethod; label: string }[] = [
  { value: "solid", label: "Solid Fill" },
  { value: "inpaint", label: "Inpaint" },
  { value: "blur", label: "Blur" },
  { value: "manual_color", label: "Manual Color" },
];

export default function ReplacementPanel({
  replacementText, onReplacementTextChange,
  fontFamily, onFontFamilyChange,
  fontSize, onFontSizeChange,
  fontColor, onFontColorChange,
  fontWeight, onFontWeightChange,
  fontStyle, onFontStyleChange,
  matchOriginal, onMatchOriginalChange,
  alignment, onAlignmentChange,
  letterSpacing, onLetterSpacingChange,
  lineHeight, onLineHeightChange,
  bgCleanup, onBgCleanupChange,
  bgColor, onBgColorChange,
  selectedCount, totalCount,
  onApplySelected, onApplyAll,
  onUndo, onRedo, onResetPage, onResetDocument,
  applying, editCount,
}: ReplacementPanelProps) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Phase 3</p>
        <h2 className="mt-1 text-xl font-bold">Replace text</h2>
        <p className="mt-1 text-sm text-muted">
          {selectedCount} of {totalCount} selected · {editCount} edit{editCount !== 1 ? "s" : ""} pending
        </p>
      </div>

      {/* Replacement text */}
      <div>
        <label className="block text-sm font-medium mb-1.5" htmlFor="replacement-text">Replacement text</label>
        <textarea
          id="replacement-text"
          value={replacementText}
          onChange={(e) => onReplacementTextChange(e.target.value)}
          placeholder="Enter replacement text…"
          rows={2}
          className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-primary resize-y"
        />
      </div>

      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-primary/30 bg-primary/10 p-3">
        <input
          type="checkbox"
          checked={matchOriginal}
          onChange={(e) => onMatchOriginalChange(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          <span className="block text-sm font-semibold text-primary">Auto-match original style</span>
          <span className="mt-0.5 block text-xs text-muted">Each match keeps its detected font, size, colour, bold and italic style.</span>
        </span>
      </label>

      {/* Font controls row */}
      <div className={`grid grid-cols-2 gap-3 ${matchOriginal ? "opacity-45" : ""}`}>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Font Family</label>
          <select
            disabled={matchOriginal}
            value={fontFamily}
            onChange={(e) => onFontFamilyChange(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary"
          >
            {FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Size (pt)</label>
          <input
            disabled={matchOriginal}
            type="number"
            min={4} max={200} step={0.5}
            value={fontSize}
            onChange={(e) => onFontSizeChange(Number(e.target.value))}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary tabular-nums"
          />
        </div>
      </div>

      {/* Color + Weight + Style */}
      <div className={`grid grid-cols-3 gap-3 ${matchOriginal ? "opacity-45" : ""}`}>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Color</label>
          <div className="flex items-center gap-2">
            <input
              disabled={matchOriginal}
              type="color"
              value={fontColor}
              onChange={(e) => onFontColorChange(e.target.value)}
              className="w-8 h-8 rounded-lg border border-border cursor-pointer"
            />
            <span className="text-xs font-mono text-muted">{fontColor}</span>
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Weight</label>
          <button
            disabled={matchOriginal}
            onClick={() => onFontWeightChange(fontWeight === "bold" ? "normal" : "bold")}
            className={`w-full rounded-lg border px-2 py-2 text-sm font-bold transition-colors ${fontWeight === "bold" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-hover"}`}
          >
            B
          </button>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Style</label>
          <button
            disabled={matchOriginal}
            onClick={() => onFontStyleChange(fontStyle === "italic" ? "normal" : "italic")}
            className={`w-full rounded-lg border px-2 py-2 text-sm italic transition-colors ${fontStyle === "italic" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-hover"}`}
          >
            I
          </button>
        </div>
      </div>

      {/* Alignment */}
      <div>
        <label className="block text-xs font-medium text-muted mb-1">Alignment</label>
        <div className="flex gap-1">
          {(["left", "center", "right"] as const).map((a) => (
            <button
              key={a}
              onClick={() => onAlignmentChange(a)}
              className={`flex-1 rounded-lg border px-2 py-2 text-xs font-medium capitalize transition-colors ${alignment === a ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-hover"}`}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* Spacing */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Letter Spacing</label>
          <input
            type="number"
            min={-5} max={20} step={0.1}
            value={letterSpacing}
            onChange={(e) => onLetterSpacingChange(Number(e.target.value))}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary tabular-nums"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted mb-1">Line Height</label>
          <input
            type="number"
            min={0.5} max={3} step={0.1}
            value={lineHeight}
            onChange={(e) => onLineHeightChange(Number(e.target.value))}
            className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary tabular-nums"
          />
        </div>
      </div>

      {/* Background cleanup */}
      <div>
        <label className="block text-xs font-medium text-muted mb-1">Background Cleanup</label>
        <select
          value={bgCleanup}
          onChange={(e) => onBgCleanupChange(e.target.value as BackgroundCleanupMethod)}
          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary"
        >
          {CLEANUP_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        {bgCleanup === "manual_color" && (
          <div className="mt-2 flex items-center gap-2">
            <input type="color" value={bgColor} onChange={(e) => onBgColorChange(e.target.value)} className="w-8 h-8 rounded border cursor-pointer" />
            <span className="text-xs font-mono text-muted">{bgColor}</span>
          </div>
        )}
      </div>

      {/* Apply buttons */}
      <div className="space-y-2 pt-2 border-t border-border">
        <button
          onClick={onApplySelected}
          disabled={applying || selectedCount === 0 || !replacementText.trim()}
          className="w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40 transition-colors hover:bg-primary-hover"
        >
          {applying ? "Applying…" : `Apply to ${selectedCount} Selected`}
        </button>
        <button
          onClick={onApplyAll}
          disabled={applying || totalCount === 0 || !replacementText.trim()}
          className="w-full rounded-xl border border-primary/30 px-4 py-2.5 text-sm font-semibold text-primary disabled:opacity-40 transition-colors hover:bg-primary/5"
        >
          Apply to All Matches
        </button>
      </div>

      {/* Undo/Redo/Reset */}
      <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
        <button onClick={onUndo} className="editor-button flex-1 text-xs">↩ Undo</button>
        <button onClick={onRedo} className="editor-button flex-1 text-xs">↪ Redo</button>
        <button onClick={onResetPage} className="editor-button flex-1 text-xs text-warning">Reset Page</button>
        <button onClick={onResetDocument} className="editor-button text-xs text-danger w-full">Reset All Edits</button>
      </div>
    </div>
  );
}
