import { useDeskmate } from '@/store/useDeskmate';
import { cx } from './ui';

/**
 * Toasts double as the notification channel for device-side events (timer
 * finished, alarm fired, reminder due) since those arrive over the socket with
 * no request behind them. Rendered in a polite live region so screen readers
 * announce them without stealing focus.
 */
export function Toasts() {
  const toasts = useDeskmate((state) => state.toasts);
  const dismiss = useDeskmate((state) => state.dismissToast);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:left-auto sm:right-6 sm:items-end"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cx(
            'animate-toast-in pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border px-4 py-3 shadow-lg backdrop-blur',
            toast.kind === 'success' && 'border-accent/30 bg-ink-900/95',
            toast.kind === 'error' && 'border-danger/40 bg-ink-900/95',
            toast.kind === 'warn' && 'border-break/40 bg-ink-900/95',
            toast.kind === 'info' && 'border-ink-700 bg-ink-900/95',
          )}
        >
          <span
            aria-hidden
            className={cx(
              'mt-1.5 size-2 shrink-0 rounded-full',
              toast.kind === 'success' && 'bg-accent',
              toast.kind === 'error' && 'bg-danger',
              toast.kind === 'warn' && 'bg-break',
              toast.kind === 'info' && 'bg-focus',
            )}
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink-100">{toast.title}</p>
            {toast.body && <p className="mt-0.5 text-xs break-words text-ink-400">{toast.body}</p>}
          </div>
          <button
            type="button"
            onClick={() => dismiss(toast.id)}
            aria-label="Dismiss notification"
            className="-mr-1 rounded p-1 text-ink-400 hover:text-ink-200 focus-visible:outline-2 focus-visible:outline-accent"
          >
            <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}
