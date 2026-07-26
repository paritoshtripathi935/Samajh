'use client';

/**
 * Two-state theme toggle: sun (light) ⇄ moon (dark).
 * Lives in the header; the icon shown represents the *opposite* of the
 * current theme (i.e. what clicking will switch to), so the affordance
 * reads "switch to light" / "switch to dark".
 */
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';

export default function ThemeToggle() {
  const { resolvedTheme, toggle } = useTheme();
  const isDark = resolvedTheme === 'dark';

  return (
    <button
      onClick={toggle}
      className="flex items-center justify-center w-8 h-8 rounded-full cursor-pointer border-0 transition-colors"
      style={{
        backgroundColor: 'transparent',
        color: 'var(--text-muted)',
      }}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  );
}
