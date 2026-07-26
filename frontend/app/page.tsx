'use client';

import { useState } from 'react';
import { FileText, MessagesSquare, Upload, Scale } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import Dialog from '@/components/Dialog';
import { Field, TextInput } from '@/components/Field';
import CitationChip from '@/components/CitationChip';
import { t } from '@/lib/design/tokens';

export default function Home() {
  const [newCaseOpen, setNewCaseOpen] = useState(false);
  const [caseName, setCaseName] = useState('');

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
          <span
            className="serif"
            style={{ fontSize: t.size.h2, fontWeight: t.weight.semibold, color: t.color.text }}
          >
            Samajh
          </span>
          <span className="serif" style={{ fontSize: t.size.h2, color: t.color.muted, marginLeft: 6 }}>
            समझ
          </span>
        </div>
        <span className="mono" style={{ fontSize: t.size.micro, color: t.color.dim }}>
          Document Intelligence · Sarvam
        </span>
        <ThemeToggle />
      </header>

      {/* Hero */}
      <main style={{ padding: t.space.xl, maxWidth: 1000, width: '100%', margin: '0 auto' }}>
        <h1
          className="serif"
          style={{
            fontSize: t.size.h1,
            fontWeight: t.weight.bold,
            color: t.color.text,
            letterSpacing: '-0.01em',
            margin: 0,
          }}
        >
          Read a 150-page filing in seconds — cited to the source.
        </h1>
        <p
          style={{
            fontSize: t.size.body,
            color: t.color.muted,
            marginTop: t.space.md,
            maxWidth: 620,
            lineHeight: 1.6,
          }}
        >
          Digitise a chargesheet or judgment, then ask questions over it. Every answer is
          grounded in the document, cites its source, and{' '}
          <strong style={{ color: t.color.accentBright }}>jumps to the exact span</strong> —
          with anything the model is unsure about flagged to verify.
        </p>

        <div style={{ display: 'flex', gap: t.space.sm, marginTop: t.space.lg }}>
          <button
            onClick={() => setNewCaseOpen(true)}
            className="inline-flex items-center cursor-pointer"
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
            <Upload size={15} /> New case
          </button>
        </div>

        {/* Workbench preview: two panes — the golden path shape. */}
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: t.space.md,
            marginTop: t.space.xl,
          }}
        >
          <Pane icon={<FileText size={15} />} title="Original filing">
            <div
              style={{
                height: 220,
                borderRadius: t.radius.sm,
                border: `1px dashed ${t.color.border}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: t.color.dim,
                fontSize: t.size.ui,
              }}
            >
              PDF renders here · click a citation to scroll + highlight
            </div>
          </Pane>

          <Pane icon={<MessagesSquare size={15} />} title="Cited answers">
            <p className="answer-prose" style={{ margin: 0 }}>
              The accused is charged under{' '}
              <span className="source-highlight">Section 302</span> and{' '}
              <span className="source-highlight">Section 34</span> IPC.{' '}
              <span className="flag-uncertain" title="Low confidence — verify against source">
                Date of offence: 14 March 2023
              </span>
              .
            </p>
            <div style={{ display: 'flex', gap: t.space.xs, marginTop: t.space.md, flexWrap: 'wrap' }}>
              <CitationChip citation={{ text: 'Section 302 IPC', citation_type: 'statute' }} />
              <CitationChip citation={{ text: 'Section 34 IPC', citation_type: 'statute' }} />
              <CitationChip
                citation={{
                  text: 'AIR 2019 SC 1234',
                  citation_type: 'case',
                  url: 'https://indiankanoon.org/search/?formInput=AIR%202019%20SC%201234',
                }}
              />
            </div>
          </Pane>
        </section>
      </main>

      {/* New-case dialog — proves Dialog + Field wiring. */}
      <Dialog
        open={newCaseOpen}
        title="New case"
        subtitle="A case holds the digitised filing(s) and your cited answers."
        onClose={() => setNewCaseOpen(false)}
        footer={
          <>
            <button
              onClick={() => setNewCaseOpen(false)}
              className="cursor-pointer"
              style={{
                padding: `${t.space.sm} ${t.space.md}`,
                background: 'transparent',
                color: t.color.muted,
                border: `1px solid ${t.color.border}`,
                borderRadius: t.radius.md,
                fontSize: t.size.ui,
              }}
            >
              Cancel
            </button>
            <button
              onClick={() => setNewCaseOpen(false)}
              disabled={!caseName.trim()}
              className="cursor-pointer disabled:opacity-50"
              style={{
                padding: `${t.space.sm} ${t.space.md}`,
                backgroundColor: t.color.accent,
                color: '#0a0a0a',
                border: 'none',
                borderRadius: t.radius.md,
                fontSize: t.size.ui,
                fontWeight: t.weight.semibold,
              }}
            >
              Create
            </button>
          </>
        }
      >
        <Field label="Case name" htmlFor="case-name" hint="e.g. State v. Sharma — CC 482/2023">
          <TextInput
            id="case-name"
            value={caseName}
            onChange={(e) => setCaseName(e.target.value)}
            placeholder="Untitled case"
            autoFocus
          />
        </Field>
      </Dialog>
    </div>
  );
}

function Pane({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        backgroundColor: t.color.raised,
        border: `1px solid ${t.color.border}`,
        borderRadius: t.radius.lg,
        padding: t.space.md,
      }}
    >
      <div
        className="flex items-center"
        style={{ gap: t.space.sm, color: t.color.muted, marginBottom: t.space.md }}
      >
        {icon}
        <span style={{ fontSize: t.size.ui, fontWeight: t.weight.semibold }}>{title}</span>
      </div>
      {children}
    </div>
  );
}
