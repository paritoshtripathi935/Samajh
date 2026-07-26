'use client';

/**
 * Theme hook — dark | light | system.
 *
 * - Writes `data-theme` on <html> so CSS `[data-theme="light"]` overrides fire.
 * - Persists the user's choice in localStorage.
 * - When the choice is `system`, listens to `prefers-color-scheme` and flips
 *   live without reload.
 *
 * The initial `data-theme` is set by an inline script in the root layout
 * (before paint) to avoid a flash; this hook keeps React in sync afterward.
 *
 * Usage:
 *   const { resolvedTheme, toggle } = useTheme();
 */
import { useEffect, useState, useCallback } from 'react';

export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'samajh:theme';

function readStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return 'dark'; // app is designed dark-first
}

function systemPrefers(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function resolve(theme: Theme): ResolvedTheme {
  return theme === 'system' ? systemPrefers() : theme;
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>('dark');
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>('dark');

  // Hydrate from storage after mount (SSR-safe: server always renders dark).
  useEffect(() => {
    const stored = readStoredTheme();
    setThemeState(stored);
    const next = resolve(stored);
    setResolvedTheme(next);
    document.documentElement.setAttribute('data-theme', next);
  }, []);

  // Apply `data-theme` to <html> whenever theme (or system preference) changes
  useEffect(() => {
    const next = resolve(theme);
    setResolvedTheme(next);
    document.documentElement.setAttribute('data-theme', next);
  }, [theme]);

  // Live-follow system preference only while `theme === 'system'`
  useEffect(() => {
    if (theme !== 'system' || typeof window === 'undefined' || !window.matchMedia) {
      return;
    }
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const handler = () => {
      const next: ResolvedTheme = mq.matches ? 'light' : 'dark';
      setResolvedTheme(next);
      document.documentElement.setAttribute('data-theme', next);
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore quota / privacy-mode errors */
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setTheme]);

  return { theme, resolvedTheme, setTheme, toggle };
}
