"use client";

import React, { useCallback, useState } from "react";
import EditorWorkspace from "@/components/editor/EditorWorkspace";
import LegalModal from "@/components/legal/LegalModal";
import UploadProgress from "@/components/upload/UploadProgress";
import UploadZone from "@/components/upload/UploadZone";
import { ApiError, deleteDocument, uploadFile } from "@/lib/api";
import { UploadState } from "@/types";

export default function HomePage() {
  const [state, setState] = useState<UploadState>({
    status: "idle", progress: 0, document: null, error: null,
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [legalModal, setLegalModal] = useState<"privacy" | "terms" | null>(null);

  const handleFileSelect = useCallback(async (file: File) => {
    setSelectedFile(file);
    setState({ status: "uploading", progress: 0, document: null, error: null });
    try {
      const document = await uploadFile(file, (progress) => {
        setState((previous) => ({
          ...previous,
          progress,
          status: progress >= 100 ? "processing" : "uploading",
        }));
      });
      setState({ status: "done", progress: 100, document, error: null });
    } catch (error) {
      const apiError = error as ApiError;
      setState({
        status: "error", progress: 0, document: null,
        error: {
          error: apiError.message || "Upload failed",
          error_code: apiError.errorCode || "UNKNOWN",
        },
      });
    }
  }, []);

  const handleReset = useCallback(async () => {
    if (state.document) {
      try {
        await deleteDocument(state.document.id);
      } catch {
        // The local editor can reset even if an old backend document expired.
      }
    }
    setState({ status: "idle", progress: 0, document: null, error: null });
    setSelectedFile(null);
  }, [state.document]);

  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-background/85 border-b border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between gap-4">
          <button onClick={handleReset} className="flex items-center gap-3 group text-left">
            <span className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </span>
            <span>
              <span className="block text-base font-bold tracking-tight">PDF Editor</span>
              <span className="block text-[11px] text-muted -mt-0.5">Find · Replace · Export</span>
            </span>
          </button>

          <div className="flex items-center gap-3">
            {state.status !== "idle" && (
              <button onClick={handleReset} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-surface-hover transition-all text-slate-300" id="reset-button">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                New Upload
              </button>
            )}
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 text-xs font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Local Mode
            </span>
          </div>
        </div>
      </header>

      <div className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8">
        {state.status === "idle" && (
          <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8 animate-fade-in">
              <h2 className="text-3xl md:text-4xl font-bold mb-3 bg-gradient-to-r from-foreground to-muted bg-clip-text text-transparent">Upload your document</h2>
              <p className="text-muted text-base max-w-md mx-auto">Files stay on this Mac while you find, replace, and export text.</p>
            </div>
            <UploadZone onFileSelect={handleFileSelect} />
          </div>
        )}

        {(state.status === "uploading" || state.status === "processing") && (
          <div className="max-w-lg mx-auto">
            <UploadProgress progress={state.progress} status={state.status} filename={selectedFile?.name ?? "Unknown file"} />
          </div>
        )}

        {state.status === "error" && state.error && (
          <div className="max-w-lg mx-auto animate-fade-in">
            <div className="glass-card p-6 rounded-2xl border-danger/20">
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-xl bg-danger/10 shrink-0">
                  <svg className="w-6 h-6 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-danger mb-1">Upload Failed</h3>
                  <p className="text-sm text-muted mb-4">{state.error.error}</p>
                  <div className="text-xs text-muted mb-4 px-3 py-2 bg-surface-hover rounded-lg font-mono">Error code: {state.error.error_code}</div>
                  <button onClick={handleReset} className="px-5 py-2.5 text-sm font-medium rounded-xl bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20" id="try-again-button">Try Again</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {state.status === "done" && state.document && <EditorWorkspace document={state.document} />}
      </div>

      <footer className="border-t border-border mt-auto py-6 bg-slate-950/60">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted">
          <span>PDF Editor v0.5 · Local Mac Mode</span>
          <div className="flex items-center gap-4">
            <button onClick={() => setLegalModal("privacy")} className="hover:text-slate-300">Privacy</button>
            <button onClick={() => setLegalModal("terms")} className="hover:text-slate-300">Terms</button>
            <span className="text-slate-500">Stored locally on this Mac</span>
          </div>
        </div>
      </footer>

      {legalModal && <LegalModal type={legalModal} isOpen={true} onClose={() => setLegalModal(null)} />}
    </main>
  );
}
