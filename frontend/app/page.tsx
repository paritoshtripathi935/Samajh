'use client';

import { useRef, useState } from 'react';
import { Scale, Upload, FileText, Languages, Gavel, Loader2, AlertTriangle } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import { api, ApiError, type ProcessResult } from '@/lib/api';
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

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('hi-IN');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function run() {
    if (!file || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.processDocument(file, { language }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header
        className="flex items-center"
        style={{
          gap: t.space.md,
          padding: `${t.space.md} ${t.space.lg}`,
          borderBottom: `1px solid ${t.color.border}`,
          backgroundColor: t.color.surface,
        }}
      >
        <Scale size={18} style={{ color: t.color.accent }} />
        <div className="flex-1">
          <span className="serif" style={{ fontSize: t.size.h2, fontWeight: t.weight.semibold, color: t.color.text }}>
            Samajh
          </span>
          <span className="serif" style={{ fontSize: t.size.h2, color: t.color.muted, marginLeft: 6 }}>
            समझ
          </span>
        </div>
        <span className="mono" style={{ fontSize: t.size.micro, color: t.color.dim }}>
          Digitise · Translate · IPC — Sarvam
        </span>
        <ThemeToggle />
      </header>

      <main style={{ padding: t.space.lg, maxWidth: 1100, width: '100%', margin: '0 auto' }}>
        <h1
          className="serif"
          style={{ fontSize: t.size.h1, fontWeight: t.weight.bold, color: t.color.text, margin: 0, letterSpacing: '-0.01em' }}
        >
          Digitise a filing, in plain English.
        </h1>
        <p style={{ fontSize: t.size.body, color: t.color.muted, marginTop: t.space.sm, maxWidth: 640, lineHeight: 1.6 }}>
          Upload a chargesheet or judgment (PDF). Samajh digitises it with Sarvam, translates it to
          English, and summarises every IPC section it cites.
        </p>

        {/* Upload card */}
        <div
          style={{
            marginTop: t.space.lg,
            backgroundColor: t.color.raised,
            border: `1px solid ${t.color.border}`,
            borderRadius: t.radius.lg,
            padding: t.space.md,
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: t.space.md,
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.zip,application/pdf"
            style={{ display: 'none' }}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
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
              borderRadius: t.radius.md,
              fontSize: t.size.ui,
            }}
          >
            <FileText size={15} /> {file ? 'Change file' : 'Choose PDF'}
          </button>

          <span style={{ fontSize: t.size.ui, color: file ? t.color.text : t.color.dim, flex: 1, minWidth: 120 }}>
            {file ? file.name : 'No file selected'}
          </span>

          <label className="inline-flex items-center" style={{ gap: t.space.xs, color: t.color.muted, fontSize: t.size.ui }}>
            <Languages size={14} />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              style={{
                background: t.color.surface,
                color: t.color.text,
                border: `1px solid ${t.color.border}`,
                borderRadius: t.radius.sm,
                padding: `6px ${t.space.sm}`,
                fontSize: t.size.ui,
              }}
            >
              {LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          <button
            onClick={run}
            disabled={!file || loading}
            className="inline-flex items-center cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              gap: t.space.sm,
              padding: `${t.space.sm} ${t.space.md}`,
              backgroundColor: t.color.accent,
              color: '#0a0a0a',
              border: 'none',
              borderRadius: t.radius.md,
              fontSize: t.size.ui,
              fontWeight: t.weight.semibold,
            }}
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
            {loading ? 'Processing…' : 'Process'}
          </button>
        </div>

        {loading && (
          <p style={{ fontSize: t.size.ui, color: t.color.dim, marginTop: t.space.md }}>
            Digitising with Sarvam, then translating + summarising IPC sections. This can take 30–90s for a
            multi-page filing.
          </p>
        )}

        {error && (
          <div
            className="flex items-start"
            style={{
              gap: t.space.sm,
              marginTop: t.space.md,
              padding: t.space.md,
              borderRadius: t.radius.md,
              border: `1px solid var(--flag-warn)`,
              backgroundColor: 'var(--flag-warn-soft)',
              color: t.color.text,
              fontSize: t.size.ui,
            }}
          >
            <AlertTriangle size={16} style={{ color: 'var(--flag-warn)', flexShrink: 0, marginTop: 1 }} />
            <span>{error}</span>
          </div>
        )}

        {result && <Results result={result} />}
      </main>
    </div>
  );
}

function Results({ result }: { result: ProcessResult }) {
  return (
    <div style={{ marginTop: t.space.lg }}>
      <div className="flex items-center" style={{ gap: t.space.sm, marginBottom: t.space.md, flexWrap: 'wrap' }}>
        {result.filing_type && (
          <span
            className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border"
            style={{ borderColor: 'var(--accent)', color: 'var(--accent-bright)', backgroundColor: 'var(--surface-active)' }}
          >
            {result.filing_type}
          </span>
        )}
        {result.document_id && (
          <span className="mono" style={{ fontSize: t.size.micro, color: t.color.dim }}>
            saved · {result.document_id.slice(0, 8)}
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: t.space.md }}>
        <Panel icon={<FileText size={15} />} title="Digitised (original)">
          <pre className="answer-prose" style={preStyle}>
            {result.raw_extraction || '—'}
          </pre>
        </Panel>
        <Panel icon={<Languages size={15} />} title="English">
          <pre className="answer-prose" style={preStyle}>
            {result.eng_extraction || '—'}
          </pre>
        </Panel>
      </div>

      <Panel icon={<Gavel size={15} />} title={`IPC sections (${result.ipc_sections.length})`} style={{ marginTop: t.space.md }}>
        {result.ipc_sections.length === 0 ? (
          <p style={{ fontSize: t.size.ui, color: t.color.dim, margin: 0 }}>No IPC sections detected.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: t.space.md }}>
            {result.ipc_sections.map((s) => (
              <div key={s.ipc} style={{ display: 'flex', gap: t.space.md, alignItems: 'flex-start' }}>
                <span
                  className="mono"
                  style={{
                    flexShrink: 0,
                    fontSize: t.size.ui,
                    fontWeight: t.weight.semibold,
                    color: 'var(--accent-bright)',
                    backgroundColor: 'var(--surface-active)',
                    border: `1px solid var(--accent)`,
                    borderRadius: t.radius.sm,
                    padding: `2px ${t.space.sm}`,
                  }}
                >
                  §{s.ipc}
                </span>
                <p className="answer-prose" style={{ margin: 0, fontSize: t.size.body }}>
                  {s.summary}
                </p>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

const preStyle: React.CSSProperties = {
  margin: 0,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  maxHeight: 420,
  overflowY: 'auto',
  fontSize: '13.5px',
};

function Panel({
  icon,
  title,
  children,
  style,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section
      style={{
        backgroundColor: t.color.raised,
        border: `1px solid ${t.color.border}`,
        borderRadius: t.radius.lg,
        padding: t.space.md,
        ...style,
      }}
    >
      <div className="flex items-center" style={{ gap: t.space.sm, color: t.color.muted, marginBottom: t.space.md }}>
        {icon}
        <span style={{ fontSize: t.size.ui, fontWeight: t.weight.semibold }}>{title}</span>
      </div>
      {children}
    </section>
  );
}
