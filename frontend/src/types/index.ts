/**
 * Shared TypeScript types for the PDF Editor frontend.
 */

export interface User {
  id: string;
  email: string;
  role: string;
  created_at: string;
  document_count: number;
  storage_used_bytes: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DashboardDocument {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  document_type: "image" | "pdf";
  width: number | null;
  height: number | null;
  page_count: number;
  created_at: string;
  updated_at: string;
  edit_count: number;
  export_status: string | null;
  latest_export_id: string | null;
}

export interface DocumentMetadata {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  document_type: "image" | "pdf";
  width: number | null;
  height: number | null;
  page_count: number;
  created_at: string;
}

export interface UploadError {
  error: string;
  error_code: string;
}

export interface UploadState {
  status: "idle" | "uploading" | "processing" | "done" | "error";
  progress: number;
  document: DocumentMetadata | null;
  error: UploadError | null;
}

export interface NormalizedBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FontEstimate {
  family: string | null;
  size: number | null;
  color: string | null;
  bold: boolean;
  italic: boolean;
}

export interface TextDetection {
  id: string;
  document_id: string;
  page_number: number;
  text: string;
  bounding_box: NormalizedBoundingBox;
  confidence: number;
  source: "native_pdf" | "ocr" | "manual";
  font: FontEstimate;
  rotation: number;
}

export interface PageAnalysis {
  page_number: number;
  content_type: "native" | "scanned" | "mixed";
  width: number;
  height: number;
}

export interface DetectionResponse {
  document_id: string;
  query: string;
  pages: PageAnalysis[];
  detections: TextDetection[];
  ocr_available: boolean;
  warnings: string[];
}

export const ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "pdf"] as const;
export const MAX_FILE_SIZE_MB = 50;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export const MIME_TYPE_MAP: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  pdf: "application/pdf",
};

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

export function getFileExtension(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

export function isAllowedFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return (ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
}

// ---- Phase 3: Edit / Replacement types ----

export type BackgroundCleanupMethod = "solid" | "inpaint" | "blur" | "manual_color";

export interface EditRecord {
  id: string;
  document_id: string;
  page_number: number;
  original_text: string;
  replacement_text: string;
  original_box: NormalizedBoundingBox;
  current_box: NormalizedBoundingBox;
  detection_source: string;
  ocr_confidence: number;
  font_family: string;
  font_size: number;
  font_color: string;
  font_weight: string;
  font_style: string;
  rotation: number;
  alignment: string;
  letter_spacing: number;
  line_height: number;
  bg_cleanup: BackgroundCleanupMethod;
  bg_color: string | null;
  timestamp: string;
  applied: boolean;
}

export interface CreateEditRequest {
  page_number: number;
  original_text: string;
  replacement_text: string;
  original_box: NormalizedBoundingBox;
  current_box?: NormalizedBoundingBox;
  detection_source?: string;
  ocr_confidence?: number;
  font_family?: string;
  font_size?: number;
  font_color?: string;
  font_weight?: string;
  font_style?: string;
  rotation?: number;
  alignment?: string;
  letter_spacing?: number;
  line_height?: number;
  bg_cleanup?: BackgroundCleanupMethod;
  bg_color?: string;
}

export interface UpdateEditRequest {
  replacement_text?: string;
  current_box?: NormalizedBoundingBox;
  font_family?: string;
  font_size?: number;
  font_color?: string;
  font_weight?: string;
  font_style?: string;
  rotation?: number;
  alignment?: string;
  letter_spacing?: number;
  line_height?: number;
  bg_cleanup?: BackgroundCleanupMethod;
  bg_color?: string;
}

export interface EditsResponse {
  edits: EditRecord[];
  count: number;
}

// ---- Phase 4: Export types ----

export type ExportFormat = "png" | "jpeg" | "webp" | "pdf" | "pdf_flattened" | "zip_images";
export type ExportMode = "preserve" | "flattened" | "image_pages" | "compressed";
export type PageSelection = "all" | "current" | "edited" | "custom";
export type ExportStatus = "queued" | "processing" | "completed" | "failed" | "cancelled" | "expired";

export interface ExportRequest {
  output_format: ExportFormat;
  mode?: ExportMode;
  page_selection?: PageSelection;
  current_page?: number;
  custom_pages?: string;
  filename?: string;
  quality?: number;
  preserve_dimensions?: boolean;
  output_width?: number;
  output_height?: number;
  flatten_edits?: boolean;
  include_metadata?: boolean;
  image_format_for_zip?: "png" | "jpeg";
}

export interface ExportJob {
  id: string;
  document_id: string;
  status: ExportStatus;
  output_format: string;
  mode: string;
  filename: string;
  mime_type: string;
  file_size: number;
  page_count: number;
  progress: number;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}
