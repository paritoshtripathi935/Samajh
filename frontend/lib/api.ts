/**
 * Thin client for the Samajh Python backend (FastAPI).
 *
 * The backend owns Sarvam (Document Intelligence, chat, translate) and the
 * database writes; the frontend never holds the Sarvam key. Point at the
 * backend with NEXT_PUBLIC_BACKEND_URL (default http://localhost:8000).
 */
import type { Answer, CaseRecord, DocumentRecord } from '@/types';

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
    throw new ApiError(`${init?.method ?? 'GET'} ${path} → ${res.status}`, res.status, body);
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

export const api = {
  health: () => request<{ status: string }>(`/health`),

  createCase: (title: string) =>
    request<CaseRecord>(`/api/cases`, { method: 'POST', body: JSON.stringify({ title }) }),

  /** Upload a filing to a case; the backend runs the Sarvam DI job. */
  uploadDocument: (caseId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<DocumentRecord>(`/api/cases/${caseId}/documents`, {
      method: 'POST',
      body: form,
    });
  },

  /** Document-typed field extraction (fields + per-field confidence). */
  extractDocument: (caseId: string, documentId: string) =>
    request<{ documentId: string; filingType: string; fields: Record<string, unknown> }>(
      `/api/cases/${caseId}/documents/${documentId}/extract`,
      { method: 'POST' },
    ),

  /** Ask a question over a case's digitised documents; returns a cited answer. */
  ask: (caseId: string, question: string) =>
    request<Answer>(`/api/cases/${caseId}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
};
