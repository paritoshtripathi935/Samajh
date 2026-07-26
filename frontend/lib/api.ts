/**
 * Client for the Samajh Python backend (FastAPI).
 *
 * The MVP endpoint is `processDocument` → one call that digitises a filing,
 * translates it to English, and summarises the IPC sections. The backend owns
 * Sarvam + Supabase; the browser never holds the Sarvam key. Point at it with
 * NEXT_PUBLIC_BACKEND_URL (default http://localhost:8000).
 */
const BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

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

export interface ProcessResult {
  raw_extraction: string;
  eng_extraction: string;
  ipc_sections: IpcSection[];
  document_id: string | null;
  filing_type: string | null;
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
  getDocument: (documentId: string) => request<unknown>(`/api/documents/${documentId}`),
};
