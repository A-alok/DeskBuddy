import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

/**
 * Last-resort boundary. A render crash inside a WebView otherwise shows a blank
 * white screen with no way back, which is a bad place to be during a demo.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack);
  }

  override render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="grid min-h-dvh place-items-center bg-ink-950 p-6">
        <div className="card max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-ink-100">Something broke</h1>
          <p className="mt-2 text-sm text-ink-400">
            The dashboard hit an unexpected error. Your device and the backend are unaffected.
          </p>
          <pre className="mt-4 max-h-40 overflow-auto rounded-lg bg-ink-950 p-3 text-left text-[11px] text-danger">
            {error.message}
          </pre>
          <div className="mt-5 flex justify-center gap-2">
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="h-10 rounded-lg border border-ink-700 px-4 text-sm text-ink-200 hover:bg-ink-850"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="h-10 rounded-lg bg-accent px-4 text-sm font-semibold text-ink-950"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
