// ── Samajh domain types ───────────────────────────────────────────────────
// One engine, two surfaces: digitise → cited Q&A → jump-to-source.

/** A chargesheet reads differently from a judgment; document-typed
 *  understanding tailors extraction + questions to the filing kind. */
export type FilingType = 'chargesheet' | 'judgment' | 'unknown';

/** Legal citation reference detected in an answer (statute/section/article
 *  or a case citation). Rendered as a CitationChip. Distinct from a
 *  SourceCitation, which points back into the digitised document. */
export interface Citation {
  text: string;
  citation_type: 'case' | 'statute';
  url?: string;
}

/** A located span in the *original* document — the thing jump-to-source
 *  scrolls+highlights. `bbox` is [x, y, width, height] in PDF point units
 *  on `page` (1-indexed); absent when DI only gives snippet-level location. */
export interface SourceSpan {
  documentId: string;
  page: number;
  bbox?: [number, number, number, number];
  /** The literal text of the span — used for the snippet-level fallback
   *  (search-and-highlight) when bbox is unavailable. */
  snippet: string;
}

/** A citation that grounds one claim in an answer back to the source. */
export interface SourceCitation extends SourceSpan {
  /** 0..1 — surfaces the "verify" flag when below the trust threshold. */
  confidence?: number;
}

export interface CaseRecord {
  id: string;
  title: string;
  createdAt: string;
}

/** A digitised document inside a case. `digitised` holds the Sarvam DI
 *  output (Markdown/JSON with layout); `pages` is the rendered page count. */
export interface DocumentRecord {
  id: string;
  caseId: string;
  fileName: string;
  fileRef: string;         // storage path / signed URL to the original PDF
  filingType: FilingType;
  pages: number;
  digitised?: unknown;     // Sarvam DI JSON (shape confirmed in M0)
  status: 'uploaded' | 'digitising' | 'ready' | 'failed';
}

/** A cited answer over one or more documents in a case. */
export interface Answer {
  id: string;
  caseId: string;
  question: string;
  answer: string;
  citations: SourceCitation[];
  /** Legal references (sections/articles/cases) surfaced in the answer. */
  legalCitations?: Citation[];
  createdAt: string;
}

/** A persisted correction — reopening the case shows the governed value. */
export interface Correction {
  id: string;
  caseId: string;
  documentId: string;
  field: string;
  originalValue: string;
  correctedValue: string;
  createdAt: string;
}
