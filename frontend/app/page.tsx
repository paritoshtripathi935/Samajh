'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Scale, Upload, FileText, Languages, Loader2, AlertTriangle } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import { api, ApiError } from '@/lib/api';
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
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('hi-IN');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function run() {
    if (!file || loading) return;
    setLoading(true);
    setError(null);
    try {
      const originalPdfUrl = URL.createObjectURL(file);
      const result = await api.processDocument(file, { language });
      // Stash for an instant render on the results page (backend fetch is the
      // shareable fallback). Guard against sessionStorage quota (big scans).
      try {
        sessionStorage.setItem('samajh:lastPdfUrl', originalPdfUrl);
      } catch {
        /* browser storage unavailable */
      }
      try {
        sessionStorage.setItem('samajh:lastResult', JSON.stringify({ ...result, fileName: file.name }));
      } catch {
        /* quota — the results page will fetch from the backend by id */
      }
      router.push(`/document/${result.document_id ?? 'local'}`);
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
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

      <main style={{ padding: t.space.lg, maxWidth: 900, width: '100%', margin: '0 auto' }}>
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
      </main>
    </div>
  );
}
