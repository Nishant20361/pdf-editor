"use client";

import React, { useState } from "react";
import { DocumentMetadata, formatFileSize } from "@/types";
import { getPreviewUrl } from "@/lib/api";

interface PdfPreviewProps {
  document: DocumentMetadata;
}

export default function PdfPreview({ document }: PdfPreviewProps) {
  const [currentPage, setCurrentPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const previewUrl = getPreviewUrl(document.id, currentPage);

  const goToPage = (page: number) => {
    if (page >= 0 && page < document.page_count) {
      setIsLoading(true);
      setCurrentPage(page);
    }
  };

  return (
    <div className="w-full animate-slide-up">
      <div className="glass-card overflow-hidden rounded-2xl">
        {/* PDF page display */}
        <div className="relative bg-[#1a1a2e] flex items-center justify-center min-h-[400px] max-h-[700px]">
          {/* Loading shimmer */}
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#1a1a2e] z-10">
              <div className="w-16 h-16 rounded-full border-4 border-border border-t-primary animate-spin" />
            </div>
          )}

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewUrl}
            alt={`Page ${currentPage + 1} of ${document.original_filename}`}
            className="relative max-w-full max-h-[700px] object-contain shadow-2xl"
            onLoad={() => setIsLoading(false)}
            onError={() => setIsLoading(false)}
            style={{ imageRendering: "auto" }}
          />
        </div>

        {/* Page navigation bar */}
        <div className="px-5 py-4 border-t border-border">
          <div className="flex items-center justify-between flex-wrap gap-3">
            {/* File info */}
            <div className="flex items-center gap-3 min-w-0">
              <div className="p-2 rounded-xl bg-danger/10">
                <svg className="w-5 h-5 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate max-w-[180px]" title={document.original_filename}>
                  {document.original_filename}
                </p>
                <p className="text-xs text-muted">
                  {formatFileSize(document.file_size)}
                  {document.width && document.height && ` · ${document.width}×${document.height} pt`}
                </p>
              </div>
            </div>

            {/* Page controls */}
            <div className="flex items-center gap-2">
              {/* First page */}
              <button
                onClick={() => goToPage(0)}
                disabled={currentPage === 0}
                className="p-2 rounded-xl hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="First page"
                title="First page"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                </svg>
              </button>

              {/* Previous */}
              <button
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage === 0}
                className="p-2 rounded-xl hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Previous page"
                title="Previous page"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              {/* Page indicator */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface-hover text-sm font-medium tabular-nums">
                <span className="text-primary">{currentPage + 1}</span>
                <span className="text-muted">/</span>
                <span className="text-muted">{document.page_count}</span>
              </div>

              {/* Next */}
              <button
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= document.page_count - 1}
                className="p-2 rounded-xl hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Next page"
                title="Next page"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>

              {/* Last page */}
              <button
                onClick={() => goToPage(document.page_count - 1)}
                disabled={currentPage >= document.page_count - 1}
                className="p-2 rounded-xl hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Last page"
                title="Last page"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                </svg>
              </button>
            </div>

            {/* PDF badge */}
            <span className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-danger/10 text-danger uppercase">
              PDF · {document.page_count} {document.page_count === 1 ? "page" : "pages"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
