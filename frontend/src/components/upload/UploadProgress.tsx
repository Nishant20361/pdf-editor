"use client";

import React from "react";

interface UploadProgressProps {
  progress: number;
  status: "uploading" | "processing";
  filename: string;
}

export default function UploadProgress({
  progress,
  status,
  filename,
}: UploadProgressProps) {
  return (
    <div className="w-full animate-fade-in">
      <div className="glass-card p-6 rounded-2xl">
        {/* File info */}
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-primary/10">
            <svg
              className="w-6 h-6 text-primary animate-pulse"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
              />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{filename}</p>
            <p className="text-xs text-muted">
              {status === "uploading" ? "Uploading..." : "Processing..."}
            </p>
          </div>
          <span className="text-sm font-semibold text-primary tabular-nums">
            {progress}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-surface-hover rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300 ease-out"
            style={{
              width: `${progress}%`,
              background:
                status === "processing"
                  ? "linear-gradient(90deg, #6366f1, #8b5cf6, #a855f7)"
                  : "linear-gradient(90deg, #6366f1, #818cf8)",
            }}
          />
        </div>

        {/* Status text */}
        <p className="text-xs text-muted mt-2 text-center">
          {status === "uploading"
            ? "Uploading file to server..."
            : "Analyzing file and generating preview..."}
        </p>
      </div>
    </div>
  );
}
