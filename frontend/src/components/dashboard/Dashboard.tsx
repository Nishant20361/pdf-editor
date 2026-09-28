"use client";

import React, { useEffect, useState } from "react";
import { DashboardDocument, DocumentMetadata } from "@/types";
import { deleteDocument, getExportDownloadUrl, getPreviewUrl, listUserDocuments } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface DashboardProps {
  onOpenDocument: (doc: DocumentMetadata) => void;
  onUploadClick: () => void;
}

export default function Dashboard({ onOpenDocument, onUploadClick }: DashboardProps) {
  const { user } = useAuth();
  const [documents, setDocuments] = useState<DashboardDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "name" | "size">("date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const res = await listUserDocuments(search, sortBy, order);
      setDocuments(res.documents);
    } catch (err) {
      console.error("Failed to load documents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [search, sortBy, order]);

  const handleDelete = async (docId: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete "${name}"? This cannot be undone.`)) {
      return;
    }
    setDeletingId(docId);
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err: any) {
      alert(err.message || "Failed to delete document");
    } finally {
      setDeletingId(null);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-8 animate-fadeIn">
      {/* Top Banner / User Quota Summary */}
      <div className="mb-8 p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-slate-800 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <span>Your Documents</span>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">
              {documents.length} files
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Private, encrypted cloud persistence for your PDF and image edits.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onUploadClick}
            className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium shadow-lg shadow-indigo-600/30 transition-all flex items-center gap-2 text-sm"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Upload New</span>
          </button>
        </div>
      </div>

      {/* Controls: Search & Sort */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-6">
        <div className="relative flex-1 max-w-md">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by filename..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
          />
          <svg
            className="w-4 h-4 absolute left-3 top-3 text-slate-500 pointer-events-none"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-400 font-medium whitespace-nowrap">Sort by:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-3 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-white text-xs focus:outline-none focus:border-indigo-500"
          >
            <option value="date">Date Uploaded</option>
            <option value="name">File Name</option>
            <option value="size">File Size</option>
          </select>

          <button
            onClick={() => setOrder(order === "asc" ? "desc" : "asc")}
            className="p-2 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-400 hover:text-white transition-colors"
            title={`Order: ${order === "asc" ? "Ascending" : "Descending"}`}
          >
            <svg
              className={`w-4 h-4 transition-transform ${order === "asc" ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Document Grid / Empty State */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-64 rounded-2xl bg-slate-900/60 border border-slate-800/80 animate-pulse" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <div className="text-center py-16 px-4 rounded-2xl bg-slate-900/40 border border-slate-800/60">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-800/60 flex items-center justify-center text-slate-500">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-bold text-white mb-1">
            {search ? "No matching documents" : "No documents yet"}
          </h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto mb-6">
            {search
              ? "Try changing your search query or clear the filter."
              : "Upload a PDF or image to begin finding and replacing text with realistic styling."}
          </p>
          <button
            onClick={onUploadClick}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium shadow-lg shadow-indigo-600/30 transition-all inline-flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Upload Document</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="group flex flex-col justify-between rounded-2xl bg-slate-900 border border-slate-800/80 hover:border-indigo-500/50 transition-all overflow-hidden shadow-lg hover:shadow-indigo-500/10"
            >
              {/* Preview Thumbnail */}
              <div
                onClick={() =>
                  onOpenDocument({
                    id: doc.id,
                    original_filename: doc.original_filename,
                    mime_type: doc.mime_type,
                    file_size: doc.file_size,
                    document_type: doc.document_type,
                    width: doc.width,
                    height: doc.height,
                    page_count: doc.page_count,
                    created_at: doc.created_at,
                  })
                }
                className="relative h-44 bg-slate-950 cursor-pointer overflow-hidden flex items-center justify-center border-b border-slate-800/80"
              >
                <img
                  src={getPreviewUrl(doc.id, 0)}
                  alt={doc.original_filename}
                  className="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-300"
                  loading="lazy"
                />
                {/* Badges */}
                <div className="absolute top-3 left-3 flex items-center gap-1.5">
                  <span
                    className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${
                      doc.document_type === "pdf"
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                        : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    }`}
                  >
                    {doc.document_type}
                  </span>
                  {doc.page_count > 1 && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-slate-800/80 text-slate-300 border border-slate-700/60">
                      {doc.page_count} pages
                    </span>
                  )}
                </div>

                {doc.edit_count > 0 && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      {doc.edit_count} {doc.edit_count === 1 ? "edit" : "edits"}
                    </span>
                  </div>
                )}
              </div>

              {/* Document Details */}
              <div className="p-4 flex-1 flex flex-col justify-between">
                <div>
                  <h3
                    onClick={() =>
                      onOpenDocument({
                        id: doc.id,
                        original_filename: doc.original_filename,
                        mime_type: doc.mime_type,
                        file_size: doc.file_size,
                        document_type: doc.document_type,
                        width: doc.width,
                        height: doc.height,
                        page_count: doc.page_count,
                        created_at: doc.created_at,
                      })
                    }
                    className="font-medium text-white text-sm truncate hover:text-indigo-400 cursor-pointer"
                    title={doc.original_filename}
                  >
                    {doc.original_filename}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-1">
                    <span>{formatFileSize(doc.file_size)}</span>
                    <span>·</span>
                    <span>{formatDate(doc.created_at)}</span>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-slate-800/80">
                  <button
                    onClick={() =>
                      onOpenDocument({
                        id: doc.id,
                        original_filename: doc.original_filename,
                        mime_type: doc.mime_type,
                        file_size: doc.file_size,
                        document_type: doc.document_type,
                        width: doc.width,
                        height: doc.height,
                        page_count: doc.page_count,
                        created_at: doc.created_at,
                      })
                    }
                    className="px-3 py-1.5 rounded-lg bg-indigo-600/10 hover:bg-indigo-600/20 text-indigo-400 text-xs font-medium border border-indigo-500/30 transition-colors flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    <span>Edit</span>
                  </button>

                  <div className="flex items-center gap-1">
                    {doc.latest_export_id && (
                      <a
                        href={getExportDownloadUrl(doc.id, doc.latest_export_id)}
                        download
                        className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                        title="Download latest export"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                      </a>
                    )}

                    <button
                      onClick={() => handleDelete(doc.id, doc.original_filename)}
                      disabled={deletingId === doc.id}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
                      title="Delete document"
                    >
                      {deletingId === doc.id ? (
                        <svg className="w-4 h-4 animate-spin text-rose-400" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
