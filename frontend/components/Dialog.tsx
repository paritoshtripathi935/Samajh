'use client';

import { useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useDismissable } from '@/hooks/useDismissable';
import { t } from '@/lib/design/tokens';

interface Props {
  open: boolean;
  /** Disables Esc + click-outside dismiss while true (e.g. during a save). */
  busy?: boolean;
  title: string;
  subtitle?: string;
  /** Footer is usually Cancel + primary CTA. */
  footer: ReactNode;
  children: ReactNode;
  onClose: () => void;
}

/**
 * Modal scaffolding — title row with close X, body, footer, click-outside
 * + Esc dismiss. Renders nothing when closed.
 */
export default function Dialog({
  open,
  busy = false,
  title,
  subtitle,
  footer,
  children,
  onClose,
}: Props) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  useDismissable(cardRef, open && !busy, onClose);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-24 px-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
    >
      <div
        ref={cardRef}
        className="w-full max-w-xl rounded-lg overflow-hidden"
        style={{
          backgroundColor: t.color.raised,
          border: `1px solid ${t.color.border}`,
          boxShadow: '0 16px 40px rgba(0,0,0,0.35)',
        }}
      >
        <header
          className="flex items-center"
          style={{
            padding: `${t.space.md} ${t.space.lg}`,
            borderBottom: `1px solid ${t.color.border}`,
            gap: t.space.sm,
          }}
        >
          <div className="flex-1 min-w-0">
            <h2
              className="serif m-0"
              style={{
                fontSize: t.size.h2,
                fontWeight: t.weight.semibold,
                color: t.color.text,
                letterSpacing: '-0.005em',
              }}
            >
              {title}
            </h2>
            {subtitle && (
              <p
                className="m-0"
                style={{
                  fontSize: t.size.ui,
                  color: t.color.muted,
                  marginTop: '2px',
                }}
              >
                {subtitle}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="cursor-pointer border-0 bg-transparent disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              padding: t.space.xs,
              color: t.color.muted,
              borderRadius: t.radius.sm,
            }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </header>

        <div style={{ padding: t.space.lg }}>{children}</div>

        <footer
          className="flex items-center justify-end"
          style={{
            gap: t.space.sm,
            padding: `${t.space.md} ${t.space.lg}`,
            borderTop: `1px solid ${t.color.border}`,
            backgroundColor: t.color.surface,
          }}
        >
          {footer}
        </footer>
      </div>
    </div>
  );
}
