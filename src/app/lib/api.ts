/**
 * Where the backend lives.
 *
 * The dashboard hardcoded http://localhost:8000 in six places, which works on
 * the machine that runs both halves and nowhere else. Deployed, the frontend is
 * served BY the backend, so same-origin relative paths are correct and there is
 * no CORS to configure.
 *
 * Resolution order:
 *   1. VITE_API_BASE, when the two are deployed separately
 *   2. localhost:8000 in dev, where Vite serves on 5173 and uvicorn on 8000
 *   3. same origin — the deployed default
 */
const EXPLICIT = import.meta.env.VITE_API_BASE?.replace(/\/$/, '');

const IS_DEV_SPLIT =
  import.meta.env.DEV &&
  typeof window !== 'undefined' &&
  window.location.port === '5173';

export const API_BASE = EXPLICIT ?? (IS_DEV_SPLIT ? 'http://localhost:8000' : '');

/** Absolute URL for an API path. `api('/debates')` → `/debates` deployed. */
export function api(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * WebSocket URL for an API path.
 *
 * The scheme has to track the page: a wss:// page cannot open a ws:// socket,
 * and every free host terminates TLS, so hardcoding ws:// breaks on deploy while
 * working perfectly in local dev.
 */
export function wsUrl(path: string): string {
  const base = API_BASE || (typeof window !== 'undefined' ? window.location.origin : '');
  return base.replace(/^http/, 'ws') + (path.startsWith('/') ? path : `/${path}`);
}
