/**
 * API client for communicating with the FastAPI backend.
 */

import {
  AuthResponse,
  CreateEditRequest,
  DashboardDocument,
  DetectionResponse,
  DocumentMetadata,
  EditRecord,
  EditsResponse,
  ExportJob,
  ExportRequest,
  UpdateEditRequest,
  UploadError,
  User,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Token storage key
const TOKEN_KEY = "pdf_editor_access_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const token = getStoredToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public errorCode: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : detail?.error || `Request failed with status ${res.status}`;
    const code = typeof detail === "object" ? detail?.error_code || "REQUEST_FAILED" : "REQUEST_FAILED";
    throw new ApiError(msg, res.status, code);
  }
  return res.json();
}

// ---- Phase 5: Authentication API ----

export async function registerUser(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await _json<AuthResponse>(res);
  if (data.access_token) {
    setStoredToken(data.access_token);
  }
  return data;
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await _json<AuthResponse>(res);
  if (data.access_token) {
    setStoredToken(data.access_token);
  }
  return data;
}

export async function getCurrentUser(): Promise<User> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: getAuthHeaders(),
  });
  return _json<User>(res);
}

export async function logoutUser(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
  } finally {
    clearStoredToken();
  }
}

export async function deleteAccount(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    await _json(res);
  } finally {
    clearStoredToken();
  }
}

// ---- Dashboard API ----

export async function listUserDocuments(
  search?: string,
  sortBy: "date" | "name" | "size" = "date",
  order: "asc" | "desc" = "desc"
): Promise<{ documents: DashboardDocument[]; total: number }> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("sort_by", sortBy);
  params.set("order", order);

  const res = await fetch(`${API_BASE}/api/documents?${params.toString()}`, {
    headers: getAuthHeaders(),
  });
  return _json(res);
}

// ---- Phase 1: Upload & Document API ----

export async function uploadFile(
  file: File,
  onProgress?: (progress: number) => void
): Promise<DocumentMetadata> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status === 201) {
          resolve(data as DocumentMetadata);
        } else {
          const detail = data.detail as UploadError;
          reject(
            new ApiError(
              detail?.error || "Upload failed",
              xhr.status,
              detail?.error_code || "UNKNOWN"
            )
          );
        }
      } catch {
        reject(new ApiError("Invalid server response", xhr.status, "PARSE_ERROR"));
      }
    });

    xhr.addEventListener("error", () => {
      reject(new ApiError("Network error during upload", 0, "NETWORK_ERROR"));
    });

    xhr.open("POST", `${API_BASE}/api/upload`);
    const token = getStoredToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.send(formData);
  });
}

export async function getDocument(docId: string): Promise<DocumentMetadata> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  await _json(res);
}

export function getPreviewUrl(docId: string, page = 0, original = false): string {
  const token = getStoredToken();
  const tokenQuery = token ? `&token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/documents/${docId}/preview?page=${page}&original=${original}${tokenQuery}`;
}

// ---- Phase 2: Detection API ----

export async function detectText(
  docId: string,
  query?: string,
  pageNumber?: number,
  caseSensitive = false,
  exactMatch = false
): Promise<DetectionResponse> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/detect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      query: query || null,
      page_number: pageNumber ?? null,
      case_sensitive: caseSensitive,
      exact_match: exactMatch,
    }),
  });
  return _json(res);
}

// ---- Phase 3: Replacement / Edits API ----

export async function createEdit(docId: string, req: CreateEditRequest): Promise<EditRecord> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(req),
  });
  return _json(res);
}

export async function listEdits(docId: string, page?: number): Promise<EditsResponse> {
  const url = page !== undefined
    ? `${API_BASE}/api/documents/${docId}/edits?page=${page}`
    : `${API_BASE}/api/documents/${docId}/edits`;
  const res = await fetch(url, { headers: getAuthHeaders() });
  return _json(res);
}

export async function updateEdit(docId: string, editId: string, req: UpdateEditRequest): Promise<EditRecord> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/${editId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(req),
  });
  return _json(res);
}

export async function deleteEdit(docId: string, editId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/${editId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  await _json(res);
}

export async function undoEdits(docId: string): Promise<EditsResponse & { success: boolean }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/undo`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export async function redoEdits(docId: string): Promise<EditsResponse & { success: boolean }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/redo`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export async function resetPage(docId: string, page: number): Promise<{ removed: number }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/reset-page/${page}`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export async function resetDocument(docId: string): Promise<{ removed: number }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/edits/reset`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export function getPreviewWithEditsUrl(docId: string, page = 0): string {
  return `${API_BASE}/api/documents/${docId}/preview-with-edits?page=${page}`;
}

// ---- Phase 4: Export API ----

export async function createExport(docId: string, req: ExportRequest): Promise<ExportJob> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/exports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(req),
  });
  return _json(res);
}

export async function getExportStatus(docId: string, exportId: string): Promise<ExportJob> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/exports/${exportId}`, {
    headers: getAuthHeaders(),
  });
  return _json(res);
}

export function getExportDownloadUrl(docId: string, exportId: string): string {
  return `${API_BASE}/api/documents/${docId}/exports/${exportId}/download`;
}

export async function deleteExport(docId: string, exportId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/exports/${exportId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(data.detail?.error || "Delete failed", res.status, data.detail?.error_code || "UNKNOWN");
  }
}
