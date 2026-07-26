'use client';

import { useEffect, type RefObject } from 'react';

/**
 * Wire Esc-to-close + click-outside dismiss to a ref'd surface.
 *
 * `enabled` gates everything: when false, no listeners are attached. Pass
 * `false` while a long-running action (DI job, LLM call, save) is in flight
 * if dropping the surface would lose work.
 */
export function useDismissable(
  ref: RefObject<HTMLElement | null>,
  enabled: boolean,
  onDismiss: () => void,
): void {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss();
    };
    const onClick = (e: MouseEvent) => {
      const el = ref.current;
      if (el && !el.contains(e.target as Node)) onDismiss();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [ref, enabled, onDismiss]);
}
