import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, HashRouter } from 'react-router-dom';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { isNative } from './lib/config';
import './index.css';

/**
 * Router choice depends on the host.
 *
 * In the Capacitor WebView the app is served from a local origin where a reload
 * on a nested path has no server to fall back to index.html, so hash routing is
 * the reliable option. On the web, real paths are nicer.
 */
const Router = isNative() ? HashRouter : BrowserRouter;

const container = document.getElementById('root');
if (!container) throw new Error('#root is missing from index.html');

createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <Router>
        <App />
      </Router>
    </ErrorBoundary>
  </StrictMode>,
);
