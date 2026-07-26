'use client';

/**
 * Pill chip for a legal reference — case (gold border) or statute/section
 * (slate border). Clicking the chip body opens the source URL in a new tab
 * (e.g. an India Code / Indian Kanoon lookup) when one is present.
 *
 * NOTE: this is the *legal-reference* chip (IPC section, article, case cite).
 * Jump-to-source into the digitised PDF is a separate affordance driven by
 * SourceCitation — see types.ts.
 */
import type { Citation } from '@/types';
import { ExternalLink } from 'lucide-react';

interface Props {
  citation: Citation;
  /** Fires when the chip body is clicked (in addition to the link, if any).
   *  Handy for scroll-to-source or analytics. */
  onSelect?: (citation: Citation) => void;
}

export default function CitationChip({ citation, onSelect }: Props) {
  const isCase = citation.citation_type === 'case';

  const borderColor = isCase ? 'var(--accent)' : 'var(--border)';
  const textColor = isCase ? 'var(--accent-bright)' : 'var(--text-muted)';
  const bgColor = isCase ? 'var(--surface-active)' : 'var(--surface-raised)';

  const chipInner = (
    <span
      className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border"
      style={{
        gap: '4px',
        borderColor,
        color: textColor,
        backgroundColor: bgColor,
        cursor: citation.url || onSelect ? 'pointer' : 'default',
      }}
    >
      {isCase ? '⚖️' : '📜'} {citation.text}
      {citation.url && <ExternalLink size={10} />}
    </span>
  );

  const handleClick = () => onSelect?.(citation);

  if (citation.url) {
    return (
      <a href={citation.url} target="_blank" rel="noopener noreferrer" onClick={handleClick}>
        {chipInner}
      </a>
    );
  }

  return (
    <span onClick={handleClick} role={onSelect ? 'button' : undefined}>
      {chipInner}
    </span>
  );
}
