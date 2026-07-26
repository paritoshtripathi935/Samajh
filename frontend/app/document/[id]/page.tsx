'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Scale, FileText, Languages, Gavel, ArrowLeft, Loader2, AlertTriangle } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import Markdown from '@/components/Markdown';
import { api, type DocumentBundle, type IpcSection, type ProcessResult } from '@/lib/api';
import { t } from '@/lib/design/tokens';

interface View {
  fileName: string;
  filingType: string | null;
  original: string;
  english: string;
  ipc: IpcSection[];
}

function fromBundle(b: DocumentBundle): View {
  return {
    fileName: b.document.file_name,
    filingType: b.document.filing_type,
    original: b.digitizations[0]?.content ?? '',
    english: b.translations[0]?.translated_text ?? '',
    ipc: b.extractions[0]?.fields?.ipc_sections ?? [],
  };
}

function fromResult(r: ProcessResult & { fileName?: string }): View {
  return {
    fileName: r.fileName ?? 'document',
    filingType: r.filing_type,
    original: r.raw_extraction,
    english: r.eng_extraction,
    ipc: r.ipc_sections,
  };
}

export default function DocumentPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      // Prefer the backend (fresh + shareable) when we have a real document id.
      if (id && id !== 'local') {
        try {
          const bundle = await api.getDocument(id);
          if (alive) setView(fromBundle(bundle));
          return;
        } catch {
          /* fall through to the just-processed result below */
        }
      }
      try {
        const raw = sessionStorage.getItem('samajh:lastResult');
        if (raw) {
          if (alive) setView(fromResult(JSON.parse(raw)));
          return;
        }
      } catch {
        /* ignore */
      }
      if (alive) setError('Could not load this document. Try processing it again.');
    }
    load();
    return () => {
      alive = false;
    };
  }, [id]);

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
        <button
          onClick={() => router.push('/')}
          className="inline-flex items-center cursor-pointer"
          style={{ gap: 6, background: 'transparent', border: 'none', color: t.color.muted, fontSize: t.size.ui }}
        >
          <ArrowLeft size={15} /> New upload
        </button>
        <div style={{ width: 1, height: 18, background: t.color.border }} />
        <Scale size={16} style={{ color: t.color.accent }} />
        <span className="serif flex-1" style={{ fontSize: t.size.h2, fontWeight: t.weight.semibold, color: t.color.text }}>
          {view?.fileName ?? 'Document'}
        </span>
        {view?.filingType && (
          <span
            className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border"
            style={{ borderColor: 'var(--accent)', color: 'var(--accent-bright)', backgroundColor: 'var(--surface-active)' }}
          >
            {view.filingType}
          </span>
        )}
        <ThemeToggle />
      </header>

      <main style={{ padding: t.space.lg, maxWidth: 1400, width: '100%', margin: '0 auto', flex: 1 }}>
        {error ? (
          <div
            className="flex items-start"
            style={{
              gap: t.space.sm,
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
        ) : !view ? (
          <div className="flex items-center" style={{ gap: t.space.sm, color: t.color.muted, fontSize: t.size.ui }}>
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: t.space.md }}>
              <Panel icon={<FileText size={15} />} title="Original (digitised)">
                {view.original ? <Markdown>{view.original}</Markdown> : <Empty />}
              </Panel>
              <Panel icon={<Languages size={15} />} title="English translation">
                {view.english ? <Markdown>{view.english}</Markdown> : <Empty />}
              </Panel>
            </div>

            <Panel icon={<Gavel size={15} />} title={`IPC sections (${view.ipc.length})`} style={{ marginTop: t.space.md }}>
              {view.ipc.length === 0 ? (
                <p style={{ fontSize: t.size.ui, color: t.color.dim, margin: 0 }}>No IPC sections detected.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: t.space.md }}>
                  {view.ipc.map((s) => (
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
                      <div style={{ flex: 1 }}>
                        <Markdown>{s.summary}</Markdown>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}
      </main>
    </div>
  );
}

function Empty() {
  return <p style={{ fontSize: t.size.ui, color: t.color.dim, margin: 0 }}>—</p>;
}

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
      <div
        className="flex items-center"
        style={{ gap: t.space.sm, color: t.color.muted, marginBottom: t.space.md, position: 'sticky' }}
      >
        {icon}
        <span style={{ fontSize: t.size.ui, fontWeight: t.weight.semibold }}>{title}</span>
      </div>
      <div style={{ maxHeight: 560, overflowY: 'auto' }}>{children}</div>
    </section>
  );
}
