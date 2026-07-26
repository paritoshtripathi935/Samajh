'use client';

import { forwardRef, type CSSProperties, type ReactNode } from 'react';
import { t } from '@/lib/design/tokens';

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}

/** Form field wrapper — uppercase micro label, control slot, optional hint. */
export function Field({ label, htmlFor, hint, children }: FieldProps) {
  return (
    <div style={{ marginBottom: t.space.md }}>
      <label
        htmlFor={htmlFor}
        style={{
          display: 'block',
          fontSize: t.size.micro,
          fontWeight: t.weight.semibold,
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          color: t.color.muted,
          marginBottom: t.space.xs,
        }}
      >
        {label}
      </label>
      {children}
      {hint && (
        <p
          className="m-0"
          style={{
            fontSize: t.size.micro,
            color: t.color.dim,
            marginTop: t.space.xs,
          }}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

const baseInputStyle: CSSProperties = {
  display: 'block',
  width: '100%',
  fontFamily: 'inherit',
  fontSize: t.size.body,
  color: t.color.text,
  backgroundColor: t.color.surface,
  border: `1px solid ${t.color.border}`,
  borderRadius: t.radius.sm,
  padding: `${t.space.sm} ${t.space.md}`,
  outline: 'none',
  transition: 'border-color 120ms',
};

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const TextInput = forwardRef<HTMLInputElement, InputProps>(
  function TextInput({ style, ...rest }, ref) {
    return <input ref={ref} {...rest} style={{ ...baseInputStyle, ...style }} />;
  },
);

type TextAreaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea({ style, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        {...rest}
        style={{
          ...baseInputStyle,
          resize: 'vertical',
          minHeight: '180px',
          ...style,
        }}
      />
    );
  },
);
