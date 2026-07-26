'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  Download,
  FileText,
  Gavel,
  ExternalLink,
  Languages,
  Loader2,
  Scale,
  Send,
  Search,
  X,
} from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import Markdown from '@/components/Markdown';
import {
  api,
  type DocumentBundle,
  type IpcSection,
  type LayoutBlock,
  type LayoutPage,
  type LegalSearchItem,
  type ProcessResult,
} from '@/lib/api';
import { t } from '@/lib/design/tokens';

type ExtractionTab = 'raw' | 'english';

interface View {
  fileName: string;
  filingType: string | null;
  original: string;
  english: string;
  ipc: IpcSection[];
  pdfUrl: string | null;
  pages: LayoutPage[];
  documentId: string | null;
  sourceLanguage: string;
}

function fromBundle(b: DocumentBundle, pdfUrl: string | null): View {
  return {
    fileName: b.document.file_name,
    filingType: b.document.filing_type,
    original: b.digitizations[0]?.content ?? '',
    english: b.translations[0]?.translated_text ?? '',
    ipc: b.extractions[0]?.fields?.ipc_sections ?? [],
    pdfUrl,
    pages: normalizePages(b.digitizations[0]?.content_json),
    documentId: b.document.id,
    sourceLanguage: b.document.source_language ?? 'auto',
  };
}

function fromResult(r: ProcessResult & { fileName?: string; sourceLanguage?: string }, pdfUrl: string | null): View {
  return {
    fileName: r.fileName ?? 'document.pdf',
    filingType: r.filing_type,
    original: r.raw_extraction,
    english: '',
    ipc: r.ipc_sections,
    pdfUrl,
    pages: normalizePages(r.pages),
    documentId: r.document_id,
    sourceLanguage: r.sourceLanguage ?? 'auto',
  };
}

export default function DocumentPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<ExtractionTab>('english');
  const [englishLoading, setEnglishLoading] = useState(false);
  const [englishError, setEnglishError] = useState<string | null>(null);
  const [englishProgress, setEnglishProgress] = useState<{ current: number; total: number } | null>(null);
  const englishStartedForRef = useRef<string | null>(null);
  const [ipcQuery, setIpcQuery] = useState('');
  const [researchSection, setResearchSection] = useState<string | null>(null);
  const [searchItems, setSearchItems] = useState<LegalSearchItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    async function load() {
      const pdfUrl = sessionStorage.getItem('samajh:lastPdfUrl');

      if (id && id !== 'local') {
        try {
          const bundle = await api.getDocument(id);
          const persistedPdfUrl = bundle.document.file_ref ? api.documentPdfUrl(id) : null;
          if (alive) setView(fromBundle(bundle, persistedPdfUrl ?? pdfUrl));
          return;
        } catch {
          /* fall through to the just-processed result below */
        }
      }

      try {
        const raw = sessionStorage.getItem('samajh:lastResult');
        if (raw) {
          if (alive) setView(fromResult(JSON.parse(raw), pdfUrl));
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

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();

    async function runEnglish() {
      if (!view || view.english) return;
      const runKey = `${view.documentId ?? view.fileName}:${view.original.length}:${view.pages.length}`;
      if (englishStartedForRef.current === runKey) return;
      englishStartedForRef.current = runKey;

      setEnglishLoading(true);
      setEnglishError(null);
      setEnglishProgress(null);
      try {
        let finalEnglish = '';
        let streamedEnglish = '';
        await api.streamEnglish(
          {
            raw_extraction: view.original,
            pages: view.pages,
            document_id: view.documentId,
            source_language: view.sourceLanguage,
          },
          (event) => {
            if (!alive) return;
            if (event.type === 'start') {
              setEnglishProgress({ current: 0, total: event.chunks });
              return;
            }
            if (event.type === 'chunk_start') {
              setEnglishProgress({ current: event.index, total: event.total });
              return;
            }
            if (event.type === 'delta') {
              streamedEnglish += event.text;
              setEnglishProgress({ current: event.index, total: event.total });
              setView((current) => (current ? { ...current, english: streamedEnglish } : current));
              return;
            }
            if (event.type === 'done') {
              finalEnglish = event.eng_extraction;
              setView((current) => (current ? { ...current, english: event.eng_extraction } : current));
            }
          },
          { signal: controller.signal },
        );
        if (!alive) return;
        try {
          const raw = sessionStorage.getItem('samajh:lastResult');
          if (raw) {
            const parsed = JSON.parse(raw);
            sessionStorage.setItem('samajh:lastResult', JSON.stringify({ ...parsed, eng_extraction: finalEnglish }));
          }
        } catch {
          /* ignore */
        }
      } catch (err) {
        if (alive && !controller.signal.aborted) setEnglishError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) {
          setEnglishLoading(false);
          setEnglishProgress(null);
        }
      }
    }
    runEnglish();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [view?.documentId, view?.fileName, view?.original, view?.pages.length, view?.sourceLanguage]);

  const activeText = tab === 'raw' ? view?.original ?? '' : view?.english ?? '';
  const stats = useMemo(() => {
    if (!view) return null;
    return {
      rawChars: view.original.length,
      englishChars: view.english.length,
      ipcCount: view.ipc.length,
      imageCount: (view.original.match(/!\[[^\]]*]\(data:image\/[^)]+\)/g) ?? []).length,
    };
  }, [view]);
  const filteredIpc = useMemo(() => {
    const query = ipcQuery.trim().toLocaleLowerCase();
    if (!view || !query) return view?.ipc ?? [];
    return view.ipc.filter(
      (section) =>
        section.ipc.toLocaleLowerCase().includes(query) ||
        section.summary.toLocaleLowerCase().includes(query),
    );
  }, [ipcQuery, view]);

  async function copyEnglish() {
    if (view?.english) await navigator.clipboard.writeText(view.english);
  }

  async function generateSectionResearch(section: IpcSection) {
    if (searchLoading) return;
    setResearchSection(section.ipc);
    setSearchItems([]);
    setSearchError(null);
    setSearchLoading(true);
    try {
      const response = await api.generateSearchItems({
        section_title: `IPC ${section.ipc} analysis`,
        section_content: section.summary,
        filing_type: view?.filingType,
      });
      setSearchItems(response.items);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearchLoading(false);
    }
  }

  async function submitDocument() {
    if (!view || submitLoading) return;
    setSubmitLoading(true);
    try {
      if (view.documentId) await api.markDocumentIngested(view.documentId);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitLoading(false);
    }
  }

function downloadMarkdown() {
    if (!view) return;
    const blob = new Blob([tab === 'raw' ? view.original : view.english], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${view.fileName.replace(/\.pdf$/i, '')}-${tab}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: t.color.bg }}>
      <header
        className="flex items-center"
        style={{
          gap: t.space.md,
          padding: `${t.space.sm} ${t.space.md}`,
          borderBottom: `1px solid ${t.color.border}`,
          backgroundColor: t.color.surface,
          minHeight: 52,
        }}
      >
        <button
          onClick={() => router.push('/')}
          className="inline-flex items-center cursor-pointer"
          style={{
            gap: 6,
            background: 'transparent',
            border: `1px solid ${t.color.border}`,
            borderRadius: t.radius.sm,
            color: t.color.muted,
            fontSize: t.size.ui,
            padding: `6px ${t.space.sm}`,
          }}
        >
          <ArrowLeft size={15} /> Upload
        </button>
        <Scale size={17} style={{ color: t.color.accent }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase' }}>
            File
          </div>
          <div className="serif" style={{ color: t.color.text, fontSize: t.size.h2, fontWeight: t.weight.semibold, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {view?.fileName ?? 'Document Review Workbench'}
          </div>
        </div>
        {view && (
          <span
            className="inline-flex items-center"
            style={{
              gap: 6,
              border: '1px solid rgba(22, 163, 74, 0.45)',
              borderRadius: t.radius.sm,
              color: '#16a34a',
              backgroundColor: 'rgba(22, 163, 74, 0.12)',
              padding: `6px ${t.space.sm}`,
              fontSize: t.size.ui,
              fontWeight: t.weight.semibold,
            }}
          >
            <CheckCircle2 size={15} /> Completed
          </span>
        )}
        <ToolbarButton onClick={copyEnglish} disabled={!view?.english} icon={<Clipboard size={15} />} label="Copy English" />
        <ToolbarButton onClick={downloadMarkdown} disabled={!view} icon={<Download size={15} />} label="Download Markdown" />
        <ToolbarButton
          onClick={submitDocument}
          disabled={submitLoading}
          icon={submitLoading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          label={submitLoading ? 'Submitting' : 'Submit'}
          primary
        />
        <ThemeToggle />
      </header>

      {error ? (
        <Message icon={<AlertTriangle size={16} />} tone="warn">{error}</Message>
      ) : !view ? (
        <Message icon={<Loader2 size={16} className="animate-spin" />}>Loading document…</Message>
      ) : (
        <main
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(300px, 0.9fr) minmax(420px, 1.35fr) minmax(300px, 0.75fr)',
            minHeight: 'calc(100vh - 52px)',
            overflow: 'hidden',
          }}
        >
          <section style={{ minWidth: 0, borderRight: `1px solid ${t.color.border}`, backgroundColor: t.color.active }}>
            <PaneHeader icon={<FileText size={15} />} title="Original PDF" detail={view.pdfUrl ? 'Browser PDF render' : 'Not available after refresh'} />
            <div style={{ height: 'calc(100vh - 104px)', padding: t.space.md, overflow: 'auto' }}>
              {view.pdfUrl ? (
                <NativePdfFrame pdfUrl={view.pdfUrl} />
              ) : view.pages.length ? (
                <AnnotatedPdfLayout pages={view.pages} pdfUrl={null} />
              ) : (
                <Empty title="Original PDF not in browser memory" text="The extraction is still available. Upload again to preview the original PDF beside it." />
              )}
            </div>
          </section>

          <section style={{ minWidth: 0, borderRight: `1px solid ${t.color.border}`, backgroundColor: t.color.surface }}>
            <div
              className="flex items-center"
              style={{ height: 52, borderBottom: `1px solid ${t.color.border}`, padding: `0 ${t.space.md}`, gap: t.space.sm }}
            >
              <TabButton active={tab === 'raw'} onClick={() => setTab('raw')} label="Raw Extraction" />
              <TabButton active={tab === 'english'} onClick={() => setTab('english')} label="English Translation" />
              <div className="mono" style={{ marginLeft: 'auto', color: t.color.dim, fontSize: t.size.micro }}>
                {activeText.length.toLocaleString()} chars
              </div>
            </div>
            <div style={{ height: 'calc(100vh - 104px)', overflow: 'auto', padding: `${t.space.lg} ${t.space.lg}` }}>
              <article
                style={{
                  maxWidth: 780,
                  margin: '0 auto',
                  backgroundColor: t.color.raised,
                  border: `1px solid ${t.color.border}`,
                  borderRadius: t.radius.md,
                  padding: t.space.lg,
                }}
              >
                {tab === 'english' && englishError ? (
                  <Empty title="English generation failed" text={englishError} />
                ) : activeText ? (
                  <>
                    {tab === 'english' && englishLoading && (
                      <div
                        className="mono"
                        style={{
                          color: t.color.dim,
                          fontSize: t.size.micro,
                          marginBottom: t.space.md,
                          textTransform: 'uppercase',
                        }}
                      >
                        Streaming English {englishProgress ? `${englishProgress.current}/${englishProgress.total}` : ''}
                      </div>
                    )}
                    <Markdown>{activeText}</Markdown>
                  </>
                ) : tab === 'english' && englishLoading ? (
                  <Empty
                    title="Generating English translation"
                    text={
                      englishProgress
                        ? `Sarvam is working through chunk ${englishProgress.current} of ${englishProgress.total}; final English tokens will appear here as soon as the model emits them.`
                        : 'Sarvam chat completions is preparing page-level chunks.'
                    }
                  />
                ) : (
                  <Empty title="No extraction" text="This response did not include text for this tab." />
                )}
              </article>
            </div>
          </section>

          <aside style={{ minWidth: 0, backgroundColor: t.color.surface, display: 'flex', flexDirection: 'column' }}>
            <PaneHeader
              icon={<Gavel size={15} />}
              title="IPC Analysis"
              detail={`${view.ipc.length} ${view.ipc.length === 1 ? 'section' : 'sections'}`}
            />
            {stats && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: t.space.sm, padding: t.space.md, borderBottom: `1px solid ${t.color.border}` }}>
                <Stat label="Raw" value={stats.rawChars.toLocaleString()} />
                <Stat label="English" value={stats.englishChars.toLocaleString()} />
                <Stat label="Images" value={stats.imageCount.toLocaleString()} />
                <Stat label="IPC" value={stats.ipcCount.toLocaleString()} />
              </div>
            )}
            <div style={{ padding: t.space.md, borderBottom: `1px solid ${t.color.border}` }}>
              <label
                className="flex items-center"
                style={{
                  gap: t.space.sm,
                  border: `1px solid ${t.color.border}`,
                  borderRadius: t.radius.sm,
                  backgroundColor: t.color.raised,
                  padding: `7px ${t.space.sm}`,
                }}
              >
                <Search size={14} style={{ color: t.color.dim, flexShrink: 0 }} />
                <input
                  value={ipcQuery}
                  onChange={(event) => setIpcQuery(event.target.value)}
                  placeholder="Search section or summary"
                  aria-label="Search IPC analysis"
                  style={{
                    minWidth: 0,
                    width: '100%',
                    border: 0,
                    outline: 0,
                    background: 'transparent',
                    color: t.color.text,
                    fontSize: t.size.ui,
                  }}
                />
                {ipcQuery && (
                  <button
                    onClick={() => setIpcQuery('')}
                    aria-label="Clear IPC search"
                    style={{ border: 0, padding: 0, background: 'transparent', color: t.color.dim, cursor: 'pointer' }}
                  >
                    <X size={14} />
                  </button>
                )}
              </label>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: t.space.md }}>
              {view.ipc.length === 0 ? (
                <Empty title="No IPC sections detected" text="The document extraction still rendered; IPC summaries will appear here when the backend detects section references." />
              ) : filteredIpc.length === 0 ? (
                <Empty title="No matching IPC sections" text={`Nothing matched “${ipcQuery.trim()}”. Try a section number or a word from the summary.`} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: t.space.md }}>
                  {filteredIpc.map((section, index) => (
                    <IpcCard
                      key={`${section.ipc}-${index}`}
                      section={section}
                      priority={index === 0}
                      selected={section.ipc === researchSection}
                      loading={searchLoading && section.ipc === researchSection}
                      onSearch={() => generateSectionResearch(section)}
                    />
                  ))}
                </div>
              )}
            </div>
            {view.ipc.length > 0 && (
              <ResearchBar
                section={researchSection}
                items={searchItems}
                loading={searchLoading}
                error={searchError}
              />
            )}
          </aside>
        </main>
      )}
    </div>
  );
}

function normalizePages(value: unknown): LayoutPage[] {
  if (Array.isArray(value)) return value.filter(isRecord) as LayoutPage[];
  if (isRecord(value) && Array.isArray(value.pages)) return value.pages.filter(isRecord) as LayoutPage[];
  return [];
}

function normalizeBlocks(blocks: unknown): LayoutBlock[] {
  if (!Array.isArray(blocks)) return [];
  return blocks.filter((block): block is LayoutBlock => isRecord(block) && normalizeBbox(block) !== null);
}

function pageNumber(page: LayoutPage): number | null {
  const value = page.page_num ?? page.page_number ?? page.page;
  return typeof value === 'number' ? value : null;
}

function inferPageSize(page: LayoutPage, blocks: LayoutBlock[]): { width: number; height: number } {
  const directWidth = numberFrom(page.width) ?? numberFrom(page.dimensions?.width);
  const directHeight = numberFrom(page.height) ?? numberFrom(page.dimensions?.height);
  if (directWidth && directHeight) return { width: directWidth, height: directHeight };

  let maxX = 0;
  let maxY = 0;
  for (const block of blocks) {
    const box = normalizeBbox(block);
    if (!box) continue;
    maxX = Math.max(maxX, box.x + box.width);
    maxY = Math.max(maxY, box.y + box.height);
  }
  return { width: maxX || 1000, height: maxY || 1414 };
}

function normalizeBbox(block: LayoutBlock): { x: number; y: number; width: number; height: number } | null {
  const raw = block.bbox ?? block.bounding_box ?? block.box;
  const box = bboxFromValue(raw);
  if (!box || box.width <= 0 || box.height <= 0) return null;
  return box;
}

function bboxFromValue(value: unknown): { x: number; y: number; width: number; height: number } | null {
  if (Array.isArray(value)) {
    if (value.length >= 4 && value.every((item) => typeof item === 'number')) {
      const [x, y, third, fourth] = value as number[];
      return { x, y, width: Math.max(0, third), height: Math.max(0, fourth) };
    }
    const points = value
      .filter(isRecord)
      .map((point) => ({ x: numberFrom(point.x), y: numberFrom(point.y) }))
      .filter((point): point is { x: number; y: number } => point.x !== null && point.y !== null);
    if (points.length >= 2) return bboxFromPoints(points);
  }

  if (isRecord(value)) {
    const x = numberFrom(value.x) ?? numberFrom(value.left);
    const y = numberFrom(value.y) ?? numberFrom(value.top);
    const width = numberFrom(value.width) ?? numberFrom(value.w);
    const height = numberFrom(value.height) ?? numberFrom(value.h);
    if (x !== null && y !== null && width !== null && height !== null) return { x, y, width, height };

    const x1 = numberFrom(value.x1);
    const y1 = numberFrom(value.y1);
    const x2 = numberFrom(value.x2);
    const y2 = numberFrom(value.y2);
    if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
      return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) };
    }
  }

  return null;
}

function bboxFromPoints(points: { x: number; y: number }[]): { x: number; y: number; width: number; height: number } {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function numberFrom(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function ToolbarButton({
  icon,
  label,
  onClick,
  disabled,
  primary = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed"
      style={{
        gap: 6,
        padding: `7px ${t.space.sm}`,
        borderRadius: t.radius.sm,
        border: primary ? 'none' : `1px solid ${t.color.border}`,
        backgroundColor: primary ? t.color.accent : t.color.raised,
        color: primary ? '#0a0a0a' : t.color.text,
        fontSize: t.size.ui,
        fontWeight: t.weight.semibold,
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function NativePdfFrame({ pdfUrl }: { pdfUrl: string }) {
  return (
    <iframe
      title="Original uploaded PDF"
      src={pdfUrl}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 620,
        border: `1px solid ${t.color.border}`,
        borderRadius: t.radius.md,
        backgroundColor: '#fff',
      }}
    />
  );
}

function AnnotatedPdfLayout({ pages, pdfUrl }: { pages: LayoutPage[]; pdfUrl: string | null }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: t.space.md }}>
      <div className="flex items-center" style={{ gap: t.space.sm }}>
        <span className="mono" style={{ color: t.color.dim, fontSize: t.size.micro }}>
          {pages.length} annotated {pages.length === 1 ? 'page' : 'pages'}
        </span>
        {pdfUrl && (
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            style={{ marginLeft: 'auto', color: t.color.accentBright, fontSize: t.size.ui, textDecoration: 'underline' }}
          >
            Open native PDF
          </a>
        )}
      </div>
      {pages.map((page, index) => (
        <AnnotatedPage key={`${pageNumber(page)}-${index}`} page={page} index={index} />
      ))}
    </div>
  );
}

function AnnotatedPage({ page, index }: { page: LayoutPage; index: number }) {
  const blocks = normalizeBlocks(page.blocks);
  const pageSize = inferPageSize(page, blocks);
  const aspectRatio = `${pageSize.width} / ${pageSize.height}`;

  return (
    <section>
      <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, marginBottom: t.space.xs }}>
        Page {pageNumber(page) ?? index + 1} · {blocks.length} blocks
      </div>
      <div
        style={{
          position: 'relative',
          aspectRatio,
          width: '100%',
          backgroundColor: '#fff',
          border: `1px solid ${t.color.border}`,
          borderRadius: t.radius.sm,
          boxShadow: '0 8px 22px rgba(0,0,0,0.16)',
          overflow: 'hidden',
        }}
      >
        {blocks.map((block, blockIndex) => (
          <BlockOverlay key={blockIndex} block={block} pageSize={pageSize} />
        ))}
      </div>
    </section>
  );
}

function BlockOverlay({ block, pageSize }: { block: LayoutBlock; pageSize: { width: number; height: number } }) {
  const box = normalizeBbox(block);
  if (!box) return null;

  const confidence = typeof block.confidence === 'number' ? block.confidence : null;
  const label = String(block.layout_tag || '').replaceAll('_', ' ') || 'text';
  const text = String(block.text || '').trim();
  const isLowConfidence = confidence !== null && confidence < 0.75;

  return (
    <div
      title={`${label}${confidence !== null ? ` · ${(confidence * 100).toFixed(0)}%` : ''}${text ? `\n${text}` : ''}`}
      style={{
        position: 'absolute',
        left: `${(box.x / pageSize.width) * 100}%`,
        top: `${(box.y / pageSize.height) * 100}%`,
        width: `${(box.width / pageSize.width) * 100}%`,
        height: `${(box.height / pageSize.height) * 100}%`,
        minWidth: 3,
        minHeight: 3,
        border: `1px solid ${isLowConfidence ? 'var(--flag-warn)' : t.color.accent}`,
        backgroundColor: isLowConfidence ? 'var(--flag-warn-soft)' : 'var(--highlight)',
        borderRadius: 2,
        overflow: 'hidden',
        color: '#111827',
        fontSize: 8,
        lineHeight: 1.15,
        padding: 1,
      }}
    >
      {text.slice(0, 42)}
    </div>
  );
}

function PaneHeader({ icon, title, detail }: { icon: React.ReactNode; title: string; detail?: string }) {
  return (
    <div
      className="flex items-center"
      style={{ gap: t.space.sm, height: 52, padding: `0 ${t.space.md}`, borderBottom: `1px solid ${t.color.border}` }}
    >
      <span style={{ color: t.color.accent }}>{icon}</span>
      <strong className="serif" style={{ color: t.color.text, fontSize: t.size.h2, fontWeight: t.weight.semibold }}>
        {title}
      </strong>
      {detail && (
        <span className="mono" style={{ marginLeft: 'auto', color: t.color.dim, fontSize: t.size.micro }}>
          {detail}
        </span>
      )}
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        height: '100%',
        border: 0,
        borderBottom: `2px solid ${active ? t.color.accent : 'transparent'}`,
        background: 'transparent',
        color: active ? t.color.text : t.color.muted,
        fontSize: t.size.ui,
        fontWeight: t.weight.semibold,
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );
}

function IpcCard({
  section,
  priority,
  selected,
  loading,
  onSearch,
}: {
  section: IpcSection;
  priority: boolean;
  selected: boolean;
  loading: boolean;
  onSearch: () => void;
}) {
  return (
    <article
      style={{
        border: `1px solid ${priority || selected ? t.color.accent : t.color.border}`,
        borderLeft: `3px solid ${priority || selected ? t.color.accent : t.color.border}`,
        borderRadius: t.radius.md,
        backgroundColor: t.color.raised,
        padding: t.space.md,
      }}
    >
      <div className="flex items-center" style={{ gap: t.space.sm }}>
        <span
          className="mono"
          style={{
            color: t.color.accentBright,
            backgroundColor: 'var(--surface-active)',
            border: `1px solid ${t.color.border}`,
            borderRadius: t.radius.sm,
            padding: `2px ${t.space.sm}`,
            fontSize: t.size.ui,
          }}
        >
          IPC {section.ipc}
        </span>
        <button
          onClick={onSearch}
          disabled={loading}
          className="inline-flex items-center"
          title={`Generate contextual legal research from the IPC ${section.ipc} analysis`}
          style={{ marginLeft: 'auto', gap: 4, border: 0, background: 'transparent', color: t.color.accentBright, fontSize: t.size.micro, cursor: 'pointer' }}
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
          {loading ? 'Researching…' : selected ? 'Research ready' : 'Search from analysis'}
        </button>
      </div>
      <div style={{ marginTop: t.space.sm }}>
        <Markdown>{section.summary || 'No summary returned.'}</Markdown>
      </div>
    </article>
  );
}

function ResearchBar({
  section,
  items,
  loading,
  error,
}: {
  section: string | null;
  items: LegalSearchItem[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <div
      aria-label="Generated legal research"
      style={{
        borderTop: `1px solid ${t.color.border}`,
        backgroundColor: t.color.raised,
        padding: t.space.sm,
        boxShadow: '0 -8px 20px rgba(0,0,0,0.12)',
      }}
    >
      <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, marginBottom: t.space.xs }}>
        {section ? `Research from IPC ${section}` : 'Contextual legal research'}
      </div>
      {loading ? (
        <div className="flex items-center" style={{ gap: t.space.xs, color: t.color.muted, fontSize: t.size.ui }}>
          <Loader2 size={13} className="animate-spin" /> Sarvam is generating queries and searching sources…
        </div>
      ) : error ? (
        <div style={{ color: 'var(--flag-warn)', fontSize: t.size.ui }}>{error}</div>
      ) : items.length === 0 ? (
        <div style={{ color: t.color.muted, fontSize: t.size.ui }}>
          Choose “Search from analysis” on a section to generate fact-specific legal research.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: t.space.sm, maxHeight: 290, overflowY: 'auto' }}>
          {items.map((item, itemIndex) => (
            <div
              key={`${item.query}-${itemIndex}`}
              style={{ border: `1px solid ${t.color.border}`, borderRadius: t.radius.sm, padding: t.space.sm }}
            >
              <strong style={{ display: 'block', color: t.color.text, fontSize: t.size.ui }}>{item.title}</strong>
              <div className="mono" style={{ color: t.color.accentBright, fontSize: t.size.micro, marginTop: 3 }}>
                {item.query}
              </div>
              <div style={{ color: t.color.muted, fontSize: t.size.micro, marginTop: 3 }}>{item.rationale}</div>
              <div style={{ display: 'flex', gap: t.space.xs, overflowX: 'auto', marginTop: t.space.xs }}>
                {item.results.length === 0 ? (
                  <span style={{ color: t.color.dim, fontSize: t.size.micro }}>No source results returned</span>
                ) : (
                  item.results.map((result) => (
                    <a
                      key={result.url}
                      href={result.url}
                      target="_blank"
                      rel="noreferrer"
                      title={result.snippet}
                      className="inline-flex items-center"
                      style={{
                        flexShrink: 0,
                        gap: 4,
                        border: `1px solid ${t.color.accent}`,
                        borderRadius: 999,
                        color: t.color.accentBright,
                        backgroundColor: t.color.active,
                        padding: `5px ${t.space.sm}`,
                        fontSize: t.size.micro,
                        textDecoration: 'none',
                      }}
                    >
                      {result.source === 'indian_kanoon' ? 'IK' : 'Web'} · {result.title.slice(0, 34)}
                      <ExternalLink size={10} />
                    </a>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: `1px solid ${t.color.border}`, borderRadius: t.radius.sm, padding: t.space.sm, backgroundColor: t.color.raised }}>
      <strong className="mono" style={{ display: 'block', color: t.color.text, fontSize: t.size.ui }}>
        {value}
      </strong>
      <span style={{ color: t.color.dim, fontSize: t.size.micro }}>{label}</span>
    </div>
  );
}

function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div style={{ border: `1px dashed ${t.color.border}`, borderRadius: t.radius.md, padding: t.space.md, color: t.color.muted, fontSize: t.size.ui }}>
      <strong style={{ display: 'block', color: t.color.text, marginBottom: t.space.xs }}>{title}</strong>
      {text}
    </div>
  );
}

function Message({ icon, children, tone }: { icon: React.ReactNode; children: React.ReactNode; tone?: 'warn' }) {
  return (
    <main style={{ padding: t.space.lg }}>
      <div
        className="flex items-start"
        style={{
          gap: t.space.sm,
          padding: t.space.md,
          borderRadius: t.radius.md,
          border: `1px solid ${tone === 'warn' ? 'var(--flag-warn)' : t.color.border}`,
          backgroundColor: tone === 'warn' ? 'var(--flag-warn-soft)' : t.color.raised,
          color: t.color.text,
          fontSize: t.size.ui,
        }}
      >
        <span style={{ color: tone === 'warn' ? 'var(--flag-warn)' : t.color.accent }}>{icon}</span>
        {children}
      </div>
    </main>
  );
}
