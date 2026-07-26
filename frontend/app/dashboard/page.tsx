'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  FolderOpen,
  Gavel,
  Languages,
  LayoutDashboard,
  Loader2,
  MessageCircle,
  Scale,
  Settings,
  Upload,
} from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import { api, ApiError, type DocumentListItem } from '@/lib/api';
import { t } from '@/lib/design/tokens';

const LANGS = [
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'en-IN', label: 'English' },
  { code: 'mr-IN', label: 'Marathi' },
  { code: 'bn-IN', label: 'Bengali' },
  { code: 'ta-IN', label: 'Tamil' },
  { code: 'te-IN', label: 'Telugu' },
  { code: 'gu-IN', label: 'Gujarati' },
];

export default function DashboardPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('hi-IN');
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let alive = true;
    async function loadDocuments() {
      setDocumentsLoading(true);
      setDocumentsError(null);
      try {
        const result = await api.listDocuments({ limit: 50 });
        if (alive) setDocuments(result.documents);
      } catch (err) {
        if (alive) setDocumentsError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) setDocumentsLoading(false);
      }
    }
    loadDocuments();
    return () => {
      alive = false;
    };
  }, []);

  const stats = useMemo(() => {
    return {
      total: documents.length,
      ready: documents.filter((doc) => doc.status === 'ready').length,
      withPdf: documents.filter((doc) => doc.file_ref).length,
    };
  }, [documents]);

  async function processFiling() {
    if (!file || processing) return;
    setProcessing(true);
    setError(null);
    try {
      const originalPdfUrl = URL.createObjectURL(file);
      const result = await api.processDocument(file, { language });
      try {
        sessionStorage.setItem('samajh:lastPdfUrl', originalPdfUrl);
      } catch {
        /* browser storage unavailable */
      }
      try {
        sessionStorage.setItem('samajh:lastResult', JSON.stringify({ ...result, fileName: file.name, sourceLanguage: language }));
      } catch {
        /* quota - the review page can fetch persisted rows by id */
      }
      router.push(`/document/${result.document_id ?? 'local'}`);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
      setProcessing(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '248px minmax(0, 1fr)', backgroundColor: t.color.bg }}>
      <aside style={{ borderRight: `1px solid ${t.color.border}`, backgroundColor: t.color.surface, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: t.space.lg, borderBottom: `1px solid ${t.color.border}` }}>
          <div className="flex items-center" style={{ gap: t.space.sm }}>
            <Scale size={20} style={{ color: t.color.accent }} />
            <div>
              <div className="serif" style={{ fontSize: 22, fontWeight: t.weight.bold, color: t.color.text }}>
                Samajh
              </div>
              <div className="mono" style={{ fontSize: t.size.micro, color: t.color.dim, textTransform: 'uppercase' }}>
                Legal AI workbench
              </div>
            </div>
          </div>
        </div>
        <nav style={{ padding: t.space.md, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <SideItem active icon={<LayoutDashboard size={16} />} label="Dashboard" />
          <SideItem icon={<FolderOpen size={16} />} label="Documents" />
          <SideItem icon={<Gavel size={16} />} label="Research" />
          <SideItem icon={<Settings size={16} />} label="Settings" />
        </nav>
        <div style={{ marginTop: 'auto', padding: t.space.md, borderTop: `1px solid ${t.color.border}` }}>
          <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase', marginBottom: t.space.xs }}>
            Ingestion
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: t.space.sm }}>
            <SidebarStat label="Files" value={stats.total} />
            <SidebarStat label="Ready" value={stats.ready} />
          </div>
        </div>
      </aside>

      <main style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <header
          className="flex items-center"
          style={{
            minHeight: 58,
            padding: `0 ${t.space.lg}`,
            borderBottom: `1px solid ${t.color.border}`,
            backgroundColor: t.color.surface,
          }}
        >
          <div>
            <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase' }}>
              Dashboard
            </div>
            <div className="serif" style={{ color: t.color.text, fontSize: t.size.h2, fontWeight: t.weight.semibold }}>
              Filing workspace
            </div>
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <ThemeToggle />
          </div>
        </header>

        <section style={{ padding: `${t.space.xl} ${t.space.lg} ${t.space.lg}` }}>
          <div style={{ maxWidth: 920, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: t.space.lg }}>
              <h1 className="serif" style={{ margin: 0, color: t.color.text, fontSize: t.size.h1, fontWeight: t.weight.bold }}>
                Digitise a filing in plain English
              </h1>
              <p style={{ margin: `${t.space.sm} auto 0`, maxWidth: 620, color: t.color.muted, fontSize: t.size.body, lineHeight: 1.6 }}>
                Upload a chargesheet or judgment. Samajh extracts readable Markdown, keeps the original PDF, and prepares the filing for legal research.
              </p>
            </div>

            <div
              style={{
                backgroundColor: t.color.raised,
                border: `1px solid ${t.color.border}`,
                borderRadius: t.radius.md,
                padding: t.space.md,
                display: 'grid',
                gridTemplateColumns: 'auto minmax(160px, 1fr) auto auto',
                alignItems: 'center',
                gap: t.space.md,
              }}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.zip,application/pdf"
                style={{ display: 'none' }}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="inline-flex items-center cursor-pointer"
                style={{
                  gap: t.space.sm,
                  padding: `${t.space.sm} ${t.space.md}`,
                  background: 'transparent',
                  color: t.color.text,
                  border: `1px solid ${t.color.border}`,
                  borderRadius: t.radius.sm,
                  fontSize: t.size.ui,
                }}
              >
                <FileText size={15} /> {file ? 'Change file' : 'Choose PDF'}
              </button>
              <span style={{ color: file ? t.color.text : t.color.dim, fontSize: t.size.ui, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {file ? file.name : 'No file selected'}
              </span>
              <label className="inline-flex items-center" style={{ gap: t.space.xs, color: t.color.muted, fontSize: t.size.ui }}>
                <Languages size={14} />
                <select
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  style={{
                    background: t.color.surface,
                    color: t.color.text,
                    border: `1px solid ${t.color.border}`,
                    borderRadius: t.radius.sm,
                    padding: `6px ${t.space.sm}`,
                    fontSize: t.size.ui,
                  }}
                >
                  {LANGS.map((lang) => (
                    <option key={lang.code} value={lang.code}>
                      {lang.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={processFiling}
                disabled={!file || processing}
                className="inline-flex items-center cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  gap: t.space.sm,
                  padding: `${t.space.sm} ${t.space.md}`,
                  backgroundColor: t.color.accent,
                  color: '#0a0a0a',
                  border: 'none',
                  borderRadius: t.radius.sm,
                  fontSize: t.size.ui,
                  fontWeight: t.weight.semibold,
                }}
              >
                {processing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                {processing ? 'Processing' : 'Digitise'}
              </button>
            </div>

            {error && <InlineError text={error} />}
          </div>
        </section>

        <section style={{ padding: `0 ${t.space.lg} ${t.space.xl}` }}>
          <div style={{ maxWidth: 1120, margin: '0 auto' }}>
            <div className="flex items-end" style={{ gap: t.space.md, marginBottom: t.space.md }}>
              <div>
                <h2 className="serif" style={{ margin: 0, color: t.color.text, fontSize: t.size.h2, fontWeight: t.weight.semibold }}>
                  Uploaded files
                </h2>
                <p style={{ margin: `${t.space.xs} 0 0`, color: t.color.muted, fontSize: t.size.ui }}>
                  Ingestion is read from the document row. Chat is available for every uploaded filing.
                </p>
              </div>
              <div className="mono" style={{ marginLeft: 'auto', color: t.color.dim, fontSize: t.size.micro }}>
                {stats.withPdf}/{stats.total} PDFs stored
              </div>
            </div>

            <div style={{ border: `1px solid ${t.color.border}`, borderRadius: t.radius.md, overflow: 'hidden', backgroundColor: t.color.raised }}>
              {documentsLoading ? (
                <TableMessage icon={<Loader2 size={16} className="animate-spin" />} title="Loading uploaded files" />
              ) : documentsError ? (
                <TableMessage icon={<AlertTriangle size={16} />} title={documentsError} />
              ) : documents.length === 0 ? (
                <TableMessage icon={<FileText size={16} />} title="No filings uploaded yet" />
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: t.size.ui }}>
                  <thead style={{ backgroundColor: t.color.surface }}>
                    <tr>
                      <Th>File</Th>
                      <Th>Type</Th>
                      <Th>Pages</Th>
                      <Th>Status</Th>
                      <Th>Ingestion</Th>
                      <Th>Chat</Th>
                      <Th>Uploaded</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr
                        key={doc.id}
                        onClick={() => router.push(`/document/${doc.id}`)}
                        style={{ cursor: 'pointer', borderTop: `1px solid ${t.color.border}` }}
                      >
                        <Td>
                          <div style={{ color: t.color.text, fontWeight: t.weight.semibold }}>{doc.file_name}</div>
                          <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro }}>{doc.id}</div>
                        </Td>
                        <Td>{doc.filing_type || 'unknown'}</Td>
                        <Td>{doc.page_count ?? '-'}</Td>
                        <Td><StatusPill status={doc.status} /></Td>
                        <Td><StatusPill status={getIngestionStatus(doc)} /></Td>
                        <Td>
                          <button
                            onClick={(event) => {
                              event.stopPropagation();
                              router.push(`/chat/${doc.id}`);
                            }}
                            aria-label={`Chat with ${doc.file_name}`}
                            className="inline-flex items-center cursor-pointer"
                            style={{
                              border: `1px solid ${t.color.border}`,
                              borderRadius: t.radius.sm,
                              backgroundColor: t.color.surface,
                              color: t.color.accentBright,
                              padding: 7,
                            }}
                          >
                            <MessageCircle size={15} />
                          </button>
                        </Td>
                        <Td>{formatDate(doc.created_at)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function SideItem({ icon, label, active = false }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <div
      className="flex items-center"
      style={{
        gap: t.space.sm,
        padding: `9px ${t.space.sm}`,
        borderRadius: t.radius.sm,
        backgroundColor: active ? t.color.active : 'transparent',
        color: active ? t.color.text : t.color.muted,
        fontSize: t.size.ui,
        fontWeight: active ? t.weight.semibold : t.weight.medium,
      }}
    >
      {icon}
      {label}
    </div>
  );
}

function SidebarStat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ border: `1px solid ${t.color.border}`, borderRadius: t.radius.sm, padding: t.space.sm, backgroundColor: t.color.raised }}>
      <div style={{ color: t.color.text, fontWeight: t.weight.semibold }}>{value}</div>
      <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro }}>{label}</div>
    </div>
  );
}

function InlineError({ text }: { text: string }) {
  return (
    <div className="flex items-start" style={{ gap: t.space.sm, marginTop: t.space.md, padding: t.space.md, borderRadius: t.radius.sm, border: `1px solid var(--flag-warn)`, backgroundColor: 'var(--flag-warn-soft)', color: t.color.text, fontSize: t.size.ui }}>
      <AlertTriangle size={16} style={{ color: 'var(--flag-warn)', flexShrink: 0, marginTop: 1 }} />
      <span>{text}</span>
    </div>
  );
}

function TableMessage({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center" style={{ gap: t.space.sm, padding: t.space.lg, color: t.color.muted }}>
      {icon}
      <span>{title}</span>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: t.space.sm, textAlign: 'left', color: t.color.dim, fontWeight: t.weight.semibold }}>{children}</th>;
}

function Td({ children }: { children: React.ReactNode }) {
  return <td style={{ padding: t.space.sm, color: t.color.muted, verticalAlign: 'top' }}>{children}</td>;
}

function StatusPill({ status }: { status: string }) {
  const normalized = status.replace(/_/g, ' ');
  const isReady = status === 'ready';
  return (
    <span
      className="inline-flex items-center"
      style={{
        gap: 6,
        border: `1px solid ${isReady ? 'rgba(22, 163, 74, 0.45)' : t.color.border}`,
        borderRadius: 999,
        color: isReady ? '#16a34a' : t.color.muted,
        backgroundColor: isReady ? 'rgba(22, 163, 74, 0.12)' : t.color.surface,
        padding: '4px 9px',
        fontSize: t.size.micro,
        fontWeight: t.weight.semibold,
        textTransform: 'uppercase',
      }}
    >
      {isReady && <CheckCircle2 size={12} />}
      {normalized}
    </span>
  );
}

function getIngestionStatus(doc: DocumentListItem) {
  const vector = doc.vector_ingestion_status ?? 'not_started';
  const structured = doc.structured_ingestion_status ?? 'not_started';
  if (vector === 'ready' && structured === 'ready') return 'ready';
  if (vector === 'failed' || structured === 'failed') return 'failed';
  if (vector === 'processing' || structured === 'processing') return 'processing';
  if (vector === 'queued' || structured === 'queued') return 'queued';
  return 'not_started';
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}
