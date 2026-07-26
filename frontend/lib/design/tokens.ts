/**
 * Samajh design tokens — the *only* place type sizes, spacing, and color
 * decisions live. Components that diverge from these are bugs.
 * (Rebuilt for Samajh; the parchment/navy look, not the source app's code.)
 *
 * Three principles, taken seriously:
 *   1. Dramatic typographic hierarchy. H1 is genuinely big. UI labels
 *      are small. The middle ground is reserved for body content.
 *   2. Selective accent. Gold only where a *decision* lives —
 *      primary CTA, active route, citation chip. Never decorative.
 *   3. Generous whitespace. Spacing tokens skip the small middle
 *      values (12, 20, 24) on purpose, so layouts can't drift into
 *      "looks even but breathes badly."
 *
 * To use from CSS-in-JS / inline styles:
 *   style={{ fontSize: t.size.h2, color: t.color.text }}
 */

export const t = {
  font: {
    /** Source Serif 4 — for case titles, headings inside content (answers,
     *  notes), the brand. Anything that should feel "legal-document-y". */
    serif:
      `'Source Serif 4', 'Source Serif Pro', Georgia, 'Times New Roman', serif`,
    /** Inter — UI chrome (buttons, navigation, sidebar, form labels). */
    sans:
      `'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif`,
    /** JetBrains Mono — citations, code, anything that's a literal string. */
    mono:
      `'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace`,
  },

  /** Type scale. Keep this list short — every extra size is a chance for
   *  visual rhythm to drift. */
  size: {
    h1: '32px',     // page title (case name on a case detail page)
    h2: '20px',     // section heading (Documents, Answers, Sources)
    body: '15px',   // normal reading text — answers, digitised paragraphs
    ui: '13px',     // navigation, buttons, table rows
    micro: '11px',  // metadata, timestamps, tags
  },

  weight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },

  /** 8-point grid, but no 12 / 20 / 24 — those middle values are where
   *  spacing-by-feel devolves. Use sparingly: most layouts only need 4
   *  values to look intentional. */
  space: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '32px',
    xl: '64px',
  },

  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    pill: '999px',
  },

  /** Color story:
   *   - text/dim/muted: the type stack — almost-black to subtle.
   *   - surface/raised/hover: the background stack — page through cards.
   *   - accent: gold (Indian, distinctive). Used ONLY for decisions.
   *   - info / warn / danger: status only.
   *   These map to the CSS variables on :root, so the theme toggle
   *   ([data-theme="light"]) swaps everything at once. */
  color: {
    text: 'var(--text)',
    dim: 'var(--text-dim)',
    muted: 'var(--text-muted)',
    bright: 'var(--text-bright, var(--text))',

    surface: 'var(--surface)',
    raised: 'var(--surface-raised)',
    active: 'var(--surface-active)',
    hover: 'var(--surface-hover)',
    bg: 'var(--bg)',

    border: 'var(--border)',

    accent: 'var(--accent)',
    accentBright: 'var(--accent-bright)',
    accentSoft: 'var(--accent-soft)',

    danger: '#dc2626',
    warn: '#d97706',
    info: '#2563eb',
    success: '#16a34a',
  },

  /** Smooth transitions — short for hovers, longer for layout shifts. */
  motion: {
    fast: '120ms cubic-bezier(0.2, 0, 0.2, 1)',
    base: '200ms cubic-bezier(0.2, 0, 0.2, 1)',
    slow: '320ms cubic-bezier(0.2, 0, 0.2, 1)',
  },
} as const;
