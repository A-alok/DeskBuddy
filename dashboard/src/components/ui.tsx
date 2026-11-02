/** Small shared UI kit. Dark theme, keyboard accessible, no extra dependencies. */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { createPortal } from 'react-dom';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

// --------------------------------------------------------------------------- //

export function Card({
  children,
  className,
  title,
  subtitle,
  actions,
}: {
  children?: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={cx('card p-4 sm:p-5', className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-sm font-semibold text-ink-200">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

// --------------------------------------------------------------------------- //

type ButtonVariant = 'primary' | 'ghost' | 'outline' | 'danger' | 'subtle';
type ButtonSize = 'sm' | 'md' | 'lg';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-ink-950 shadow-[var(--shadow-neo-glow)] hover:opacity-90 active:shadow-[var(--shadow-neo-pressed)] font-semibold',
  ghost: 'text-ink-300 hover:bg-ink-850 hover:shadow-[var(--shadow-neo-sm)] hover:text-ink-200 active:shadow-[var(--shadow-neo-pressed)]',
  outline: 'border border-ink-800 text-ink-200 shadow-[var(--shadow-neo-sm)] active:shadow-[var(--shadow-neo-pressed)] hover:bg-ink-900',
  danger: 'border border-danger/40 text-danger hover:bg-danger/10 shadow-[var(--shadow-neo-sm)] active:shadow-[var(--shadow-neo-pressed)]',
  subtle: 'bg-ink-900 text-ink-200 shadow-[var(--shadow-neo-sm)] hover:bg-ink-850 active:shadow-[var(--shadow-neo-pressed)]',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
};

export function Button({
  variant = 'subtle',
  size = 'md',
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg transition-colors select-none',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'disabled:cursor-not-allowed disabled:opacity-40',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// --------------------------------------------------------------------------- //

export function Badge({
  children,
  tone = 'neutral',
  className,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info';
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: 'bg-ink-800 text-ink-300',
    good: 'bg-accent/15 text-accent',
    warn: 'bg-break/15 text-break',
    bad: 'bg-danger/15 text-danger',
    info: 'bg-focus/15 text-focus',
  };
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = 'neutral', pulse = false }: { tone?: 'good' | 'bad' | 'warn' | 'neutral'; pulse?: boolean }) {
  const tones: Record<string, string> = {
    good: 'bg-accent',
    bad: 'bg-danger',
    warn: 'bg-break',
    neutral: 'bg-ink-600',
  };
  return <span aria-hidden className={cx('inline-block size-2 rounded-full', tones[tone], pulse && 'animate-pulse')} />;
}

// --------------------------------------------------------------------------- //

export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={htmlFor} className="text-xs font-medium text-ink-300">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-ink-400">{hint}</p>}
    </div>
  );
}

const INPUT_CLASS =
  'h-10 w-full rounded-xl border border-ink-900 bg-ink-950 px-3 text-sm text-ink-200 placeholder:text-ink-600 ' +
  'shadow-[var(--shadow-neo-pressed)] focus:border-accent focus:shadow-[var(--shadow-neo-glow)] focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent transition-shadow';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(INPUT_CLASS, className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(INPUT_CLASS, 'pr-8', className)} {...rest}>
      {children}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        'relative h-6 w-11 shrink-0 rounded-full transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'disabled:cursor-not-allowed disabled:opacity-40',
        checked ? 'bg-accent shadow-[var(--shadow-neo-glow)]' : 'bg-ink-950 shadow-[var(--shadow-neo-pressed)] border border-ink-900',
      )}
    >
      <span
        aria-hidden
        className={cx(
          'absolute top-0.5 size-5 rounded-full bg-white transition-all',
          checked ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  );
}

// --------------------------------------------------------------------------- //

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'accent' | 'focus' | 'break';
}) {
  const tones: Record<string, string> = {
    accent: 'text-accent',
    focus: 'text-focus',
    break: 'text-break',
  };
  return (
    <div className="card p-3 sm:p-4">
      <p className="text-[11px] tracking-wide text-ink-400 uppercase">{label}</p>
      <p className={cx('tabular mt-1 text-xl font-semibold sm:text-2xl', tone ? tones[tone] : 'text-ink-200')}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[11px] text-ink-400">{sub}</p>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-ink-700 px-4 py-8 text-center">
      <p className="text-sm font-medium text-ink-300">{title}</p>
      {body && <p className="max-w-sm text-xs text-ink-400">{body}</p>}
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-ink-100 sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        'inline-block size-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent',
        className,
      )}
    />
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
}) {
  if (!open || typeof document === 'undefined') return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="fixed inset-0 cursor-pointer" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md rounded-3xl border border-ink-800 bg-ink-900 p-6 shadow-[var(--shadow-neo)] z-10 max-h-[90vh] overflow-y-auto">
        {title && (
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-ink-800/80">
            <div className="text-base font-bold text-ink-100">{title}</div>
            <button
              type="button"
              onClick={onClose}
              className="size-8 rounded-xl bg-ink-950 border border-ink-800 hover:bg-ink-850 text-ink-400 hover:text-ink-200 flex items-center justify-center text-xs font-bold transition-all cursor-pointer"
            >
              ✕
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}

