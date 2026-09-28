"use client";

import React, { useCallback, useRef, useState, DragEvent } from "react";
import {
  isAllowedFile,
  formatFileSize,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_MB,
  ALLOWED_EXTENSIONS,
} from "@/types";

interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  disabled?: boolean;
}

export default function UploadZone({ onFileSelect, disabled }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndSelect = useCallback(
    (file: File) => {
      setClientError(null);

      if (!isAllowedFile(file.name)) {
        setClientError(
          `Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(", ").toUpperCase()}`
        );
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setClientError(
          `File too large (${formatFileSize(file.size)}). Maximum: ${MAX_FILE_SIZE_MB} MB`
        );
        return;
      }

      if (file.size === 0) {
        setClientError("File is empty.");
        return;
      }

      onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (disabled) return;

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        validateAndSelect(files[0]);
      }
    },
    [disabled, validateAndSelect]
  );

  const handleDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) setIsDragging(true);
    },
    [disabled]
  );

  const handleDragLeave = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
    },
    []
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        validateAndSelect(files[0]);
      }
      // Reset input value so the same file can be re-selected
      e.target.value = "";
    },
    [validateAndSelect]
  );

  const handleClick = useCallback(() => {
    if (!disabled) {
      fileInputRef.current?.click();
    }
  }, [disabled]);

  return (
    <div className="w-full animate-fade-in">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") handleClick();
        }}
        aria-label="Upload file drop zone"
        className={`
          relative flex flex-col items-center justify-center
          w-full min-h-[280px] rounded-2xl border-2 border-dashed
          cursor-pointer transition-all duration-300 ease-out
          ${
            isDragging
              ? "border-primary bg-primary/5 scale-[1.01] shadow-lg shadow-primary/10"
              : "border-border hover:border-primary/50 hover:bg-surface-hover"
          }
          ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}
        `}
      >
        {/* Upload icon */}
        <div
          className={`
            mb-5 p-4 rounded-2xl transition-all duration-300
            ${isDragging ? "bg-primary/10 scale-110" : "bg-surface-hover"}
          `}
        >
          <svg
            className={`w-10 h-10 transition-colors duration-300 ${
              isDragging ? "text-primary" : "text-muted"
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>

        {/* Text */}
        <h3 className="text-lg font-semibold mb-1">
          {isDragging ? "Drop your file here" : "Drag & drop your file"}
        </h3>
        <p className="text-muted text-sm mb-4">or click to browse</p>

        {/* File type badges */}
        <div className="flex flex-wrap gap-2 justify-center">
          {["JPG", "JPEG", "PNG", "PDF"].map((ext) => (
            <span
              key={ext}
              className="px-3 py-1 text-xs font-medium rounded-full
                bg-surface-hover text-muted border border-border
                transition-colors duration-200"
            >
              {ext}
            </span>
          ))}
        </div>

        {/* Size limit */}
        <p className="text-muted text-xs mt-3">
          Max {MAX_FILE_SIZE_MB} MB
        </p>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.pdf"
          onChange={handleFileInput}
          className="hidden"
          aria-hidden="true"
          id="file-upload-input"
        />
      </div>

      {/* Client-side error */}
      {clientError && (
        <div
          className="mt-4 flex items-center gap-3 px-4 py-3 rounded-xl
            bg-danger/10 border border-danger/20 text-danger text-sm
            animate-fade-in"
          role="alert"
        >
          <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>{clientError}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setClientError(null);
            }}
            className="ml-auto p-1 hover:bg-danger/10 rounded-lg transition-colors"
            aria-label="Dismiss error"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
