/**
 * Citation extractor — pull structured Indian legal references out of an
 * answer's text. Supports AIR / SCC / SCR / ILR case formats plus
 * Section / Article references. Ported to TS from the source app's Python
 * formatter; the regexes are the reusable knowledge here.
 *
 * For a chargesheet, "under which sections?" is a core question — so
 * section/article detection turns a plain answer into clickable chips.
 */
import type { Citation } from '@/types';

const PATTERNS: Record<string, RegExp> = {
  // AIR 2023 SC 1234  /  AIR 2022 Bom 567
  air: /AIR\s+\d{4}\s+[A-Z][A-Za-z]+\s+\d+/g,
  // (2023) 5 SCC 678
  scc: /\(\d{4}\)\s+\d+\s+SCC\s+\d+/g,
  // 2023 SCR 1 45
  scr: /\d{4}\s+SCR\s+\d+\s+\d+/g,
  // ILR 2022 Delhi 890
  ilr: /ILR\s+\d{4}\s+[A-Z][A-Za-z]+\s+\d+/g,
  // Section 302 of the Indian Penal Code  /  Section 138 NI Act
  section:
    /[Ss]ection\s+\d+[A-Z]?(?:\([a-z]\))?(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][A-Za-z\s]{2,30})?(?=[\s,.;]|$)/g,
  // Article 21 of the Constitution
  article:
    /[Aa]rticle\s+\d+[A-Z]?(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][A-Za-z\s]{2,30})?(?=[\s,.;]|$)/g,
};

const CASE_TYPES = new Set(['air', 'scc', 'scr', 'ilr']);

/** Extract all Indian legal citations from a block of text. */
export function extractCitations(text: string): Citation[] {
  const citations: Citation[] = [];
  const seen = new Set<string>();

  for (const [ctype, pattern] of Object.entries(PATTERNS)) {
    for (const match of text.matchAll(pattern)) {
      const raw = match[0].trim();
      if (seen.has(raw)) continue;
      seen.add(raw);

      const kind: Citation['citation_type'] = CASE_TYPES.has(ctype) ? 'case' : 'statute';
      const url = kind === 'case' ? buildIkSearchUrl(raw) : undefined;
      citations.push({ text: raw, citation_type: kind, url });
    }
  }

  return citations;
}

/**
 * Parse a "Suggested Next Steps" section from a structured answer.
 * Returns a list of plain-text step strings.
 */
export function extractSuggestedSteps(text: string): string[] {
  const sectionMatch = text.match(
    /\*{0,2}Suggested Next Steps\*{0,2}\s*:?\s*\n([\s\S]*?)(?=\n\*{0,2}[A-Z]|$)/i,
  );
  if (!sectionMatch) return [];

  const steps: string[] = [];
  for (const rawLine of sectionMatch[1].split('\n')) {
    const line = rawLine.trim();
    const stepMatch = line.match(/^(?:\d+[.)]\s*|-\s*)(.+)$/);
    if (stepMatch) steps.push(stepMatch[1].trim());
  }
  return steps;
}

/** Build an Indian Kanoon search URL for a citation string. */
export function buildIkSearchUrl(citation: string): string {
  return `https://indiankanoon.org/search/?formInput=${encodeURIComponent(citation)}`;
}
