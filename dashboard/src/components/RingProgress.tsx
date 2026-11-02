import type { ReactNode } from 'react';
import { cx } from './ui';

/**
 * Circular progress. `value` is 0..1 and is clamped — a countdown that overruns
 * by a fraction of a second should not draw a broken arc.
 */
export function RingProgress({
  value,
  size = 200,
  thickness = 10,
  tone = 'accent',
  children,
  label,
  className,
}: {
  value: number;
  size?: number;
  thickness?: number;
  tone?: 'accent' | 'focus' | 'break' | 'danger';
  children?: ReactNode;
  label: string;
  className?: string;
}) {
  const clamped = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * clamped;

  const strokes: Record<string, string> = {
    accent: 'stroke-accent',
    focus: 'stroke-focus',
    break: 'stroke-break',
    danger: 'stroke-danger',
  };

  return (
    <div className={cx('relative inline-grid place-items-center', className)} style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
        role="img"
        aria-label={label}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          className="stroke-ink-800"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          className={cx('transition-[stroke-dasharray] duration-200 ease-linear', strokes[tone])}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}
