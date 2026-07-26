/**
 * Client for the Samajh Python backend (FastAPI).
 *
 * The MVP endpoint is `processDocument` → one call that digitises a filing,
 * translates it to English, and summarises the IPC sections. The backend owns
 * Sarvam + Supabase; the browser never holds the Sarvam key. Point at it with
 * NEXT_PUBLIC_BACKEND_URL (default http://localhost:8000).
 */
const BASE = process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly body?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init?.headers,
    },
  });
  const text = await res.text();
  const body = text ? safeJson(text) : undefined;
  if (!res.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : '';
    throw new ApiError(
      `${init?.method ?? 'GET'} ${path} → ${res.status}${detail ? `: ${detail}` : ''}`,
      res.status,
      body,
    );
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export interface IpcSection {
  ipc: string;
  summary: string;
}

export interface LayoutBlock {
  text?: string;
  bbox?: unknown;
  bounding_box?: unknown;
  box?: unknown;
  layout_tag?: string;
  confidence?: number;
  reading_order?: number;
  [key: string]: unknown;
}

export interface LayoutPage {
  page_num?: number;
  page_number?: number;
  page?: number;
  width?: number;
  height?: number;
  dimensions?: { width?: number; height?: number };
  blocks?: LayoutBlock[];
  [key: string]: unknown;
}

export interface ProcessResult {
  raw_extraction: string;
  eng_extraction: string;
  ipc_sections: IpcSection[];
  pages?: LayoutPage[] | null;
  document_id: string | null;
  filing_type: string | null;
}

export interface DocumentBundle {
  document: {
    id: string;
    file_name: string;
    filing_type: string;
    source_language: string | null;
    page_count: number | null;
    status: string;
    created_at: string;
  };
  digitizations: {
    id: string;
    output_format: string;
    content: string | null;
    content_json: unknown;
    sarvam_job_id: string | null;
    created_at: string;
  }[];
  extractions: {
    id: string;
    filing_type: string | null;
    fields: { ipc_sections?: IpcSection[] } & Record<string, unknown>;
    model: string | null;
    created_at: string;
  }[];
  translations: {
    id: string;
    target_language: string;
    source_language: string | null;
    translated_text: string;
    model: string | null;
    created_at: string;
  }[];
}

export const api = {
  health: () => request<{ status: string }>(`/health`),

  /** MVP: upload a filing → digitise + translate to English + IPC summaries. */
  processDocument: (file: File, opts?: { language?: string }) => {
    const form = new FormData();
    form.append('file', file);
    if (opts?.language) form.append('language', opts.language);
    return request<ProcessResult>(`/api/documents/process`, { method: 'POST', body: form });
  },

  /** The persisted document + its digitizations / extractions / translations. */
  getDocument: (documentId: string) => request<DocumentBundle>(`/api/documents/${documentId}`),
};
