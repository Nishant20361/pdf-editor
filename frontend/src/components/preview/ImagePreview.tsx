"use client";

import React from "react";
import { DocumentMetadata, formatFileSize } from "@/types";
import { getPreviewUrl } from "@/lib/api";

interface ImagePreviewProps {
  document: DocumentMetadata;
}

export default function ImagePreview({ document }: ImagePreviewProps) {
  const previewUrl = getPreviewUrl(document.id);

  return (
    <div className="w-full animate-slide-up">
      <div className="glass-card overflow-hidden rounded-2xl">
        {/* Image container */}
        <div className="relative bg-[#0a0a0a] flex items-center justify-center min-h-[300px] max-h-[600px]">
          {/* Checkerboard pattern for transparency */}
          <div
            className="absolute inset-0 opacity-10"
            style={{
              backgroundImage:
                "linear-gradient(45deg, #333 25%, transparent 25%), linear-gradient(-45deg, #333 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #333 75%), linear-gradient(-45deg, transparent 75%, #333 75%)",
              backgroundSize: "16px 16px",
              backgroundPosition: "0 0, 0 8px, 8px -8px, -8px 0px",
            }}
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewUrl}
            alt={document.original_filename}
            className="relative max-w-full max-h-[600px] object-contain"
            style={{ imageRendering: "auto" }}
          />
        </div>

        {/* Metadata bar */}
        <div className="px-5 py-4 border-t border-border">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {/* Filename */}
            <div className="flex items-center gap-2 min-w-0">
              <svg className="w-4 h-4 text-muted shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span className="text-sm font-medium truncate max-w-[200px]" title={document.original_filename}>
                {document.original_filename}
              </span>
            </div>

            {/* Dimensions */}
            {document.width && document.height && (
              <div className="flex items-center gap-1.5">
                <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
                <span className="text-sm text-muted tabular-nums">
                  {document.width} × {document.height}
                </span>
              </div>
            )}

            {/* File size */}
            <div className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              <span className="text-sm text-muted">
                {formatFileSize(document.file_size)}
              </span>
            </div>

            {/* Type badge */}
            <span className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-primary/10 text-primary uppercase">
              {document.mime_type.split("/")[1]}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
