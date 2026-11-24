import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import type { DebateView, HistoryEntry, JudgeLog } from '../types/debate';

interface UseDebateHistoryReturn {
  history: HistoryEntry[] | null;
  logs: JudgeLog[] | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  openDebate: any | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setOpenDebate: (d: any | null) => void;
}

/**
 * Fetches debate history and judge logs when the user switches to those tabs.
 *
 * Data is loaded lazily (when the tab is opened, not on mount) so the dashboard
 * does not pay for data that most sessions never look at.  It is re-fetched on
 * every tab open so a debate finished since the last visit shows up.
 */
export function useDebateHistory(view: DebateView): UseDebateHistoryReturn {
  const [history, setHistory] = useState<HistoryEntry[] | null>(null);
  const [logs, setLogs] = useState<JudgeLog[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [openDebate, setOpenDebate] = useState<any | null>(null);

  useEffect(() => {
    if (view === 'active') return;

    const url = view === 'history'
      ? api('/debates?limit=50')
      : api('/judge/logs?limit=100');

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(url);
        const data = await res.json();
        if (cancelled) return;
        if (view === 'history') setHistory(data.debates ?? []);
        else setLogs(data.logs ?? []);
      } catch {
        if (cancelled) return;
        // Empty array, not null: null means "still loading", and a backend that
        // is down should read as "nothing here" rather than spin forever.
        if (view === 'history') setHistory([]);
        else setLogs([]);
      }
    })();

    return () => { cancelled = true; };
  }, [view]);

  return { history, logs, openDebate, setOpenDebate };
}
