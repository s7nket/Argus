import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  History, 
  Gavel,
  Radio,
  Zap,
  Scale,
  X,
  Brain,
  ArrowLeft,
  Share2,
  Check,
  FileDown,
  Loader2
} from 'lucide-react';
import { cn } from '../lib/utils';
import { api, wsUrl } from '../lib/api';
import { useNavigate } from 'react-router';
import { exportAndShareDebatePdf } from '../lib/pdfExport';

/**
 * Coerce a judge field to renderable text.
 *
 * The verdict schema asks for strings, but the model occasionally answers a
 * request for "3 sentences: who won, what the loser got wrong, the turning
 * point" with an object keyed by those three parts. Rendering that object
 * crashes the whole dashboard with "Objects are not valid as a React child",
 * losing a completed debate the user just waited minutes for.
 *
 * The backend coerces these too; this is the second line of defence, because a
 * malformed field should degrade one paragraph, never the page.
 */
function asText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(' ');
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(asText).filter(Boolean).join(' ');
  }
  return String(value);
}

export function DebateDashboard() {
  const navigate = useNavigate();
  const [judgeOpen, setJudgeOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [isDebating, setIsDebating] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);
  const [typingAgent, setTypingAgent] = useState<string | null>(null);
  const [debateComplete, setDebateComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Transient status the server pushes while it waits out a rate limit.
  // Distinct from `error`: the debate has not failed, it is just slow.
  const [notice, setNotice] = useState<string | null>(null);
  const [judgeStatus, setJudgeStatus] = useState<'online' | 'offline' | 'checking'>('checking');
  const [view, setView] = useState<'active' | 'history' | 'logs'>('active');
  const [history, setHistory] = useState<any[] | null>(null);
  const [logs, setLogs] = useState<any[] | null>(null);
  const [openDebate, setOpenDebate] = useState<any | null>(null);
  // Real backend state for the sidebar identity card. The card used to read
  // "OPERATOR-01 / ACTIVE SESSION", which is a user account this system does not
  // have; the useful thing to show in that slot is which judge is actually
  // running and what it has to verify against.
  const [stack, setStack] = useState<{ model?: string; scorer?: string; ftOnline?: boolean; docs?: number }>({});
  // Two rounds of two exchanges each: four speeches per side, which matches
  // a real debate format. Three rounds of three was nine per side and took
  // about five minutes.
  const rounds = 2;
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const typingStartRef = useRef<number>(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const judgeFailuresRef = useRef(0);
  const debateCompleteRef = useRef(false);
  const errorOccurredRef = useRef(false);
  const [debateId, setDebateId] = useState<string | null>(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfExported, setPdfExported] = useState<'downloaded' | 'shared' | null>(null);
  const [historyPdfExported, setHistoryPdfExported] = useState(false);
  const [humanSide, setHumanSide] = useState<'pro' | 'con' | null>(null);
  const [humanTurn, setHumanTurn] = useState<{ role: string; round: number; sub_round: number } | null>(null);
  const [humanInput, setHumanInput] = useState('');

  const handleExportPdf = async () => {
    if (isExportingPdf || messages.length === 0) return;
    setIsExportingPdf(true);
    try {
      await exportAndShareDebatePdf({
        topic: prompt || 'AI Debate Session',
        debateId: debateId,
        messages: messages,
        stack: stack,
        createdAt: new Date().toISOString(),
      });
      setPdfExported('downloaded');
      setTimeout(() => setPdfExported(null), 3500);
    } catch (e) {
      console.error('PDF export failed:', e);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleExportHistoryDebate = async (debate: any) => {
    if (!debate || isExportingPdf) return;
    setIsExportingPdf(true);
    try {
      const reconstructedMessages: any[] = [];
      (debate.rounds ?? []).forEach((r: any) => {
        reconstructedMessages.push({
          type: 'sub_round_divider',
          round: r.round,
          label: `Round ${r.round} Exchanges`,
        });
        (r.exchange ?? []).forEach((ex: any) => {
          reconstructedMessages.push({
            type: ex.speaker === 'pro' ? 'pro' : 'con',
            round: r.round,
            sub_round: ex.sub_round || 1,
            text: ex.text,
            model: ex.model || debate.scorer || 'unknown',
            latency: ex.latency || 0,
          });
        });
        reconstructedMessages.push({
          type: 'verdict',
          round: r.round,
          data: {
            pro_scores: r.pro_scores,
            con_scores: r.con_scores,
            round_winner: r.round_winner,
            reasoning: r.reasoning,
          },
        });
      });

      if (debate.final_verdict) {
        reconstructedMessages.push({
          type: 'final_verdict',
          data: debate.final_verdict,
        });
      }

      await exportAndShareDebatePdf({
        topic: debate.topic || 'Archived Debate',
        debateId: debate.id,
        messages: reconstructedMessages,
        finalVerdict: debate.final_verdict,
        stack: { scorer: debate.scorer },
        createdAt: debate.created_at,
      });
      setHistoryPdfExported(true);
      setTimeout(() => setHistoryPdfExported(false), 3500);
    } catch (e) {
      console.error('History PDF export failed:', e);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const sendHumanArgument = () => {
    if (!wsRef.current || !humanInput.trim()) return;
    wsRef.current.send(JSON.stringify({ type: 'human_argument', text: humanInput.trim() }));
    // We do NOT append locally to `messages` here.
    // The backend orchestrator will immediately broadcast the argument back
    // over the WebSocket (as `pro_argument` / `con_argument`), which will append it.
    setHumanInput('');
    setHumanTurn(null);
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typingAgent]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  useEffect(() => {
    const checkJudge = async () => {
      try {
        const res = await fetch(api('/judge/health'));
        const data = await res.json();
        setStack(s => ({ ...s, model: data.model, scorer: data.scorer, ftOnline: data.ft_online }));
        if (data.status === 'online') {
          judgeFailuresRef.current = 0;
          setJudgeStatus('online');
          return;
        }
        judgeFailuresRef.current += 1;
        if (judgeFailuresRef.current >= 2) {
          setJudgeStatus('offline');
        }
      } catch {
        judgeFailuresRef.current += 1;
        if (judgeFailuresRef.current >= 2) {
          setJudgeStatus('offline');
        }
      }
    };

    setJudgeStatus('checking');
    checkJudge();
    const interval = setInterval(checkJudge, 5000);

    // Corpus size is fetched once, not polled: it only changes when the corpus
    // is rebuilt, and it has no business on a 5-second timer.
    fetch(api('/status'))
      .then(r => r.json())
      .then(d => setStack(s => ({ ...s, docs: d?.vector_db?.evidence_count })))
      .catch(() => { /* card degrades to the judge line alone */ });

    return () => clearInterval(interval);
  }, []);

  const handleStartDebate = React.useCallback((e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (typingAgent) return;

    // Used to return here silently on an empty topic — a click or an Enter
    // press produced literally nothing, which is indistinguishable from the
    // button being broken. The button below is now disabled for the same
    // condition, but Enter-to-submit bypasses a disabled button in some
    // browsers, so this path needs its own feedback too.
    if (!prompt.trim()) {
      setError('Enter a debate topic first.');
      return;
    }

    if (judgeStatus === 'offline') {
      setError('Judge is offline. Check that the backend is running and GROQ_API_KEY is set in backend/.env.');
      return;
    }
    setIsDebating(true);
    setMessages([]);
    setTypingAgent(null);
    setDebateComplete(false);
    setNotice(null);
    setDebateId(null);
    setPdfExported(null);
    debateCompleteRef.current = false;
    errorOccurredRef.current = false;
    setError(null);

    const ws = new WebSocket(wsUrl('/ws/debate'));
    wsRef.current = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ topic: prompt, rounds, human_side: humanSide }));
      // Browsers cannot emit WS ping frames; agent generation can leave the
      // socket silent for 30-60s, long enough for a middlebox to drop the idle
      // connection (close 1006). A periodic outbound frame keeps it warm.
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, 15000);
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'agent_typing':
          setNotice(null);
          setTypingAgent(msg.agent);
          typingStartRef.current = Date.now();
          break;
        case 'sub_round_start':
          setMessages(prev => [...prev, { type: 'sub_round_divider', round: msg.round, sub_round: msg.sub_round, label: msg.label }]);
          break;
        case 'pro_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'pro', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: msg.model || 'unknown' }]);
          break;
        }
        case 'con_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'con', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: msg.model || 'unknown' }]);
          break;
        }
        case 'round_verdict':
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'verdict', round: msg.round, data: msg.data }]);
          break;
        case 'final_verdict':
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'final_verdict', data: msg.data }]);
          break;
        case 'debate_end':
          setNotice(null);
          debateCompleteRef.current = true;
          setDebateComplete(true);
          setTypingAgent(null);
          break;
        // The server confirms it picked the debate up before making any upstream
        // call. Without this the topic parse — which can stall on a rate limit —
        // leaves the UI blank and looks like the button did nothing.
        case 'accepted':
          setNotice('Starting debate\u2026');
          break;
        case 'debate_start':
          if (msg.debate_id) setDebateId(msg.debate_id);
          break;
        case 'human_turn':
          setTypingAgent(null);
          setHumanTurn({ role: msg.role, round: msg.round, sub_round: msg.sub_round });
          break;
        // A call is waiting out a rate limit or a transient error. These waits
        // run to minutes, so they have to be visible.
        case 'notice':
          setNotice(msg.message);
          break;
        case 'error':
          errorOccurredRef.current = true;
          setError(msg.message);
          setNotice(null);
          setTypingAgent(null);
          break;
      }
    };
    ws.onerror = () => {
      errorOccurredRef.current = true;
      setError('WebSocket connection failed. Is the backend running?');
      setTypingAgent(null);
      setIsDebating(false);
    };
    ws.onclose = () => {
      if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null; }
      wsRef.current = null;
      setTypingAgent(null);
      setIsDebating(false);
      if (!debateCompleteRef.current && !errorOccurredRef.current) {
        setError('Connection lost. The debate was interrupted.');
      }
    };
  }, [prompt, rounds, typingAgent, judgeStatus, humanSide]);

  // Fetched when the tab is opened rather than on mount, so the dashboard does
  // not pay for data most sessions never look at. Refetched on every open so a
  // debate finished since the last visit shows up.
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

  const hasStarted = isDebating || messages.length > 0;

  return (
    <div className="flex h-screen w-full bg-[#0a0a0c] text-white font-sans overflow-hidden selection:bg-white/20">
      
      {/* Sidebar */}
      <aside className="w-[280px] shrink-0 bg-[#161618] flex flex-col justify-between hidden md:flex z-20">
        <div>
          <div className="h-20 flex items-center px-8 cursor-pointer" onClick={() => navigate('/')}>
            <span className="font-['Orbitron'] font-bold text-2xl tracking-widest text-white/90">ARGUS</span>
          </div>
          {/* Which judge is actually running, and what it can verify against.
              The scorer line matters because the fine-tuned model silently falls
              back to Groq whenever its tunnel drops, and that swap changes how
              every score in the session was produced. */}
          <div className="px-8 py-6 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-black border border-white/10 flex items-center justify-center shrink-0">
              <Scale className="w-[18px] h-[18px] text-white/60" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-['Orbitron'] text-xs font-bold text-white tracking-widest">
                {stack.ftOnline ? 'ARGUSCORE-4B' : 'JUDGE-0'}
              </span>
              <div className="flex items-center gap-1.5 mt-1">
                <div className={cn(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  judgeStatus === 'online'   && (stack.ftOnline ? "bg-emerald-500" : "bg-amber-400"),
                  judgeStatus === 'offline'  && "bg-red-500",
                  judgeStatus === 'checking' && "bg-yellow-400 animate-pulse",
                )} />
                <span className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest uppercase truncate">
                  {judgeStatus === 'checking'
                    ? 'Connecting'
                    : judgeStatus === 'offline'
                      ? 'Judge offline'
                      : stack.ftOnline ? 'Fine-tuned scorer' : 'Groq fallback'}
                </span>
              </div>
              {stack.docs != null && (
                <span className="font-['JetBrains_Mono'] text-[9px] text-white/25 tracking-widest uppercase mt-1">
                  {stack.docs.toLocaleString()} evidence docs
                </span>
              )}
            </div>
          </div>
          <nav className="px-4 mt-8 flex flex-col gap-1.5">
            {([
              { id: 'active', label: 'ACTIVE DEBATES', icon: Radio },
              { id: 'history', label: 'DEBATE HISTORY', icon: History },
              { id: 'logs', label: 'JUDGE LOGS', icon: Gavel },
            ] as const).map((item) => {
              const active = view === item.id;
              return (
              <button
                key={item.id}
                onClick={() => { setView(item.id); setOpenDebate(null); }}
                className={cn("flex items-center gap-4 px-4 py-3 rounded-xl text-left transition-colors duration-200 relative", active ? "active bg-white/[0.06] text-white" : "text-white/40 hover:text-white hover:bg-white/[0.02]")}>
                {active && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-1/2 bg-white rounded-r-md" />}
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">{item.label}</span>
              </button>
              );
            })}
          </nav>
        </div>
        <div className="p-6 flex flex-col gap-3">
          {/* Judge Status Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5">
            <span
              className={cn(
                "w-2 h-2 rounded-full shrink-0",
                judgeStatus === 'online'   && "bg-emerald-400 shadow-[0_0_6px_#34d399]",
                judgeStatus === 'offline'  && "bg-red-500 shadow-[0_0_6px_#ef4444]",
                judgeStatus === 'checking' && "bg-yellow-400 animate-pulse"
              )}
            />
            <span className={cn(
              "font-['JetBrains_Mono'] text-[10px] tracking-widest font-bold uppercase",
              judgeStatus === 'online'   && "text-emerald-400",
              judgeStatus === 'offline'  && "text-red-400",
              judgeStatus === 'checking' && "text-yellow-400"
            )}>
              JUDGE {judgeStatus === 'checking' ? 'CHECKING...' : judgeStatus.toUpperCase()}
            </span>
          </div>
          <button onClick={() => navigate('/')} className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors duration-200">
            <ArrowLeft className="w-4 h-4" />
            <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">Main Landing</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 relative h-full">
        {/* The "SIMULATION PROTOCOL V4.2.0" strapline and the outlined
            INITIALIZING ARENA banner were removed: a fixed version string and a
            state label already shown elsewhere, overlaying the content they sat
            on top of. The heading stays for screen readers. */}
        <h1 className="sr-only">Debate Dashboard</h1>

        {view === 'history' ? (
          <div className="flex-1 overflow-y-auto p-6">
            {openDebate ? (
              <div className="max-w-3xl mx-auto">
                <button onClick={() => setOpenDebate(null)} className="flex items-center gap-2 mb-6 text-white/40 hover:text-white transition-colors">
                  <ArrowLeft className="w-4 h-4" />
                  <span className="font-['JetBrains_Mono'] text-[11px] tracking-widest uppercase">Back to history</span>
                </button>
                <div className="flex items-start justify-between gap-4 mb-6">
                  <div>
                    <h2 className="font-['Orbitron'] text-lg text-white/90 mb-1">{asText(openDebate.topic)}</h2>
                    <p className="font-['JetBrains_Mono'] text-[10px] text-white/35 tracking-widest uppercase">
                      {new Date(openDebate.created_at).toLocaleString()} · {(openDebate.rounds ?? []).length} rounds
                    </p>
                  </div>
                  <button
                    onClick={() => handleExportHistoryDebate(openDebate)}
                    disabled={isExportingPdf}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl border border-emerald-500/30 hover:border-emerald-500/60 bg-emerald-500/[0.08] hover:bg-emerald-500/[0.15] text-emerald-300 transition-all text-xs font-['JetBrains_Mono'] tracking-wider shrink-0 cursor-pointer active:scale-95 disabled:opacity-50"
                  >
                    {isExportingPdf ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                    ) : historyPdfExported ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <FileDown className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    <span>
                      {isExportingPdf
                        ? 'Exporting…'
                        : historyPdfExported
                        ? 'PDF Downloaded!'
                        : 'Export PDF'}
                    </span>
                  </button>
                </div>
                {(openDebate.rounds ?? []).map((r: any) => (
                  <div key={r.round} className="mb-4 bg-white/[0.03] border border-white/[0.08] rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-['JetBrains_Mono'] text-[11px] font-bold text-white/70 tracking-widest uppercase">Round {r.round}</span>
                      <span className="font-['JetBrains_Mono'] text-[11px] text-white/50">
                        PRO {r.pro_scores?.total} · CON {r.con_scores?.total} → {String(r.round_winner).toUpperCase()}
                      </span>
                    </div>
                    <p className="font-['DM_Sans'] text-xs text-white/55 leading-snug">{asText(r.reasoning)}</p>
                  </div>
                ))}
                {openDebate.final_verdict?.verdict && (
                  <div className="bg-indigo-500/[0.06] border border-indigo-500/25 rounded-2xl p-5">
                    <span className="font-['JetBrains_Mono'] text-[11px] font-bold text-indigo-400 tracking-widest uppercase">Final Verdict</span>
                    <p className="font-['DM_Sans'] text-sm text-white/80 leading-relaxed mt-2">{asText(openDebate.final_verdict.verdict)}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="max-w-3xl mx-auto">
                <h2 className="font-['Orbitron'] text-lg tracking-[0.15em] text-white/70 uppercase mb-6">Debate History</h2>
                {history === null && <p className="font-['JetBrains_Mono'] text-xs text-white/30 tracking-widest uppercase">Loading…</p>}
                {history?.length === 0 && (
                  <p className="font-['DM_Sans'] text-sm text-white/35">No debates recorded yet. Run one and it will appear here.</p>
                )}
                {history?.map((d) => (
                  <button key={d.id} onClick={async () => {
                    try {
                      const res = await fetch(api(`/debates/${d.id}`));
                      setOpenDebate(await res.json());
                    } catch { /* leave the list up rather than blanking the view */ }
                  }} className="w-full text-left mb-3 bg-white/[0.03] hover:bg-white/[0.05] border border-white/[0.08] rounded-2xl p-4 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-['DM_Sans'] text-sm text-white/85 truncate">{asText(d.topic)}</p>
                        <p className="font-['JetBrains_Mono'] text-[10px] text-white/35 tracking-widest uppercase mt-1">
                          {new Date(d.created_at).toLocaleString()} · {d.rounds} rounds · {asText(d.scorer)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        {d.error ? (
                          <span className="font-['JetBrains_Mono'] text-[10px] text-red-400 tracking-widest uppercase">Aborted</span>
                        ) : (
                          <>
                            <span className={cn("font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase",
                              d.is_tie ? "text-white/50" : d.winner === 'pro' ? "text-emerald-400" : "text-rose-400")}>
                              {d.is_tie ? 'TIE' : String(d.winner ?? '').toUpperCase()}
                            </span>
                            <p className="font-['JetBrains_Mono'] text-[10px] text-white/35 mt-0.5">{d.pro_total} · {d.con_total}</p>
                          </>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : view === 'logs' ? (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-3xl mx-auto">
              <h2 className="font-['Orbitron'] text-lg tracking-[0.15em] text-white/70 uppercase mb-2">Judge Logs</h2>
              <p className="font-['DM_Sans'] text-xs text-white/35 mb-6">
                Per-round audit: which scorer ran, what the corpus could verify, and how far the two blind passes disagreed.
              </p>
              {logs === null && <p className="font-['JetBrains_Mono'] text-xs text-white/30 tracking-widest uppercase">Loading…</p>}
              {logs?.length === 0 && (
                <p className="font-['DM_Sans'] text-sm text-white/35">No judged rounds yet. Run a debate and its audit trail will appear here.</p>
              )}
              {logs?.map((l, i) => (
                <div key={`${l.debate_id}-${l.round}-${i}`} className="mb-3 bg-white/[0.03] border border-white/[0.08] rounded-2xl p-4">
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <p className="font-['DM_Sans'] text-sm text-white/80 truncate">{asText(l.topic)}</p>
                    <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase shrink-0">R{l.round}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 font-['JetBrains_Mono'] text-[10px] text-white/45 mb-2">
                    <span>PRO {l.pro_total} · CON {l.con_total} → {String(l.winner ?? '').toUpperCase()}</span>
                    <span>scorer: {asText(l.scorer)}</span>
                    {l.verification_backend && <span>nli: {asText(l.verification_backend)}</span>}
                    {l.blind_passes != null && <span>passes: {l.blind_passes}</span>}
                    {l.label_disagreement != null && <span>bias δ: {l.label_disagreement}</span>}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 font-['JetBrains_Mono'] text-[10px] text-white/40 mb-2">
                    {l.pro_coverage != null && <span>pro coverage: {l.pro_coverage}</span>}
                    {l.con_coverage != null && <span>con coverage: {l.con_coverage}</span>}
                    {!!l.pro_repetition_penalty && <span className="text-amber-400/70">pro rep −{l.pro_repetition_penalty}</span>}
                    {!!l.con_repetition_penalty && <span className="text-amber-400/70">con rep −{l.con_repetition_penalty}</span>}
                    {l.fallacy && <span className="text-rose-400/70">{asText(l.fallacy)}</span>}
                  </div>
                  {(l.pro_evidence_cited?.length > 0 || l.con_evidence_cited?.length > 0) && (
                    <div className="grid sm:grid-cols-2 gap-3 mt-3 pt-3 border-t border-white/[0.06]">
                      <div>
                        <p className="font-['JetBrains_Mono'] text-[9px] text-emerald-400/70 tracking-widest uppercase mb-1">PRO cited</p>
                        {(l.pro_evidence_cited ?? []).slice(0, 3).map((e: any, k: number) => (
                          <p key={k} className="font-['DM_Sans'] text-[11px] text-white/45 leading-snug mb-0.5">· {asText(e)}</p>
                        ))}
                        {(l.pro_evidence_cited ?? []).length === 0 && <p className="font-['DM_Sans'] text-[11px] text-white/25">nothing verifiable</p>}
                      </div>
                      <div>
                        <p className="font-['JetBrains_Mono'] text-[9px] text-rose-400/70 tracking-widest uppercase mb-1">CON cited</p>
                        {(l.con_evidence_cited ?? []).slice(0, 3).map((e: any, k: number) => (
                          <p key={k} className="font-['DM_Sans'] text-[11px] text-white/45 leading-snug mb-0.5">· {asText(e)}</p>
                        ))}
                        {(l.con_evidence_cited ?? []).length === 0 && <p className="font-['DM_Sans'] text-[11px] text-white/25">nothing verifiable</p>}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : !hasStarted ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 mt-10">
            <div className="flex flex-col items-center max-w-[400px] text-center">
              <div className="w-32 h-32 rounded-full border border-dashed border-white/10 flex items-center justify-center mb-10 relative">
                <div className="absolute inset-0 rounded-full bg-white/[0.01]" />
                <div className="w-12 h-12 bg-white/5 rounded-full flex items-center justify-center"><Brain className="w-5 h-5 text-white/30" /></div>
              </div>
              <h2 className="font-['Orbitron'] text-xl tracking-[0.2em] text-white/60 mb-4 uppercase font-semibold">Awaiting Parameters</h2>
              <p className="font-['DM_Sans'] text-sm text-white/30 leading-relaxed font-medium mb-8">Enter a debate topic below to engage neural simulation protocols and deploy active agents.</p>

              {/* Mode selector */}
              <div className="flex items-center gap-2 p-1 bg-white/[0.04] border border-white/[0.06] rounded-full mb-10">
                {([
                  { value: null,  label: '🤖 AI vs AI' },
                  { value: 'pro', label: '🧑 I\'m PRO' },
                  { value: 'con', label: '🧑 I\'m CON' },
                ] as const).map(({ value, label }) => (
                  <button
                    key={String(value)}
                    onClick={() => setHumanSide(value)}
                    className={cn(
                      "flex-1 py-2 px-3 rounded-full font-['JetBrains_Mono'] text-[10px] tracking-widest uppercase font-bold transition-all",
                      humanSide === value
                        ? 'bg-white text-black shadow'
                        : 'text-white/40 hover:text-white'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {judgeStatus === 'offline' && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center mb-6">
                  <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-red-500/20 bg-red-500/5 max-w-md w-full text-left">
                    <span className="mt-0.5 text-red-400 shrink-0">⚠</span>
                    <div>
                      <p className="font-['JetBrains_Mono'] text-[11px] font-bold text-red-400 tracking-widest uppercase mb-1">Judge Offline</p>
                      <p className="font-['DM_Sans'] text-sm text-red-300/80 leading-relaxed">
                        Scores need Kaggle FT judge (port 8002 → FT_JUDGE_URL in backend/.env). Verdicts use JUDGE_GROQ_API_KEY on Groq. Restart the backend after updating .env. Status refreshes every 5 seconds.
                      </p>
                    </div>
                  </div>
                </motion.div>
              )}

              {error && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center mb-6">
                  <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-6 py-4 text-center max-w-md">
                    <span className="font-['JetBrains_Mono'] text-xs text-red-400 tracking-widest">{error}</span>
                  </div>
                </motion.div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 md:px-20 lg:px-40 pt-32 pb-40 flex flex-col gap-6 scroll-smooth z-0">
            {messages.length === 0 && isDebating && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center my-auto py-20 text-center">
                <div className="w-16 h-16 rounded-full border border-dashed border-emerald-400/40 flex items-center justify-center mb-6 animate-[spin_8s_linear_infinite]">
                  <Zap className="w-6 h-6 text-emerald-400" />
                </div>
                <h3 className="font-['Orbitron'] text-sm tracking-[0.2em] text-white/80 uppercase font-semibold mb-2">
                  Initializing Arena Protocol
                </h3>
                <p className="font-['JetBrains_Mono'] text-xs text-white/40 tracking-wider uppercase">
                  {notice || 'Deploying autonomous debaters & judge agent…'}
                </p>
              </motion.div>
            )}

            {messages.map((msg, idx) => {
              if (msg.type === 'sub_round_divider') {
                const subColors: Record<number, string> = { 1: 'text-sky-400/70 border-sky-500/20', 2: 'text-amber-400/70 border-amber-500/20', 3: 'text-violet-400/70 border-violet-500/20' };
                const colorClass = subColors[msg.sub_round] ?? 'text-white/40 border-white/10';
                return (
                  <motion.div key={idx} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-4">
                    <div className="h-[1px] bg-white/[0.04] flex-1" />
                    <div className={`border px-4 py-1.5 rounded-full ${colorClass}`}>
                      <span className="font-['JetBrains_Mono'] text-[9px] tracking-[0.2em] uppercase font-bold">
                        R{msg.round} · {msg.label.toUpperCase()}
                      </span>
                    </div>
                    <div className="h-[1px] bg-white/[0.04] flex-1" />
                  </motion.div>
                );
              }
              if (msg.type === 'pro') {
                return (
                  <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-col gap-2.5 max-w-3xl will-change-[transform,opacity] transform-gpu">
                    <div className="flex items-center gap-3 w-full">
                      <div className="bg-white/10 px-3 py-1 rounded-full border border-white/10 shrink-0">
                        <span className="font-['JetBrains_Mono'] text-[10px] text-white tracking-widest font-bold">AGENT-01</span>
                      </div>
                      <span className="font-['JetBrains_Mono'] text-[9px] text-white/30 tracking-widest uppercase">{msg.model}</span>
                      <div className="h-[1px] bg-white/[0.05] flex-1" />
                      <span className="font-['JetBrains_Mono'] text-[10px] text-emerald-400/80 tracking-widest font-bold">PRO</span>
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest">R{msg.round}</span>
                    </div>
                    <p className="font-['DM_Sans'] text-[15px] text-white/80 leading-[1.6] font-light">{msg.text}</p>
                    <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center gap-6">
                      <span>MODEL: {msg.model}</span>
                      <span>LATENCY: {msg.latency}ms</span>
                    </div>
                  </motion.div>
                );
              }
              if (msg.type === 'con') {
                return (
                  <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-col gap-2.5 max-w-3xl self-end text-left will-change-[transform,opacity] transform-gpu">
                    <div className="flex items-center gap-3 w-full justify-end">
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest">R{msg.round}</span>
                      <span className="font-['JetBrains_Mono'] text-[10px] text-rose-400/80 tracking-widest font-bold">CON</span>
                      <div className="h-[1px] bg-white/[0.05] flex-1" />
                      <span className="font-['JetBrains_Mono'] text-[9px] text-white/30 tracking-widest uppercase">{msg.model}</span>
                      <div className="bg-white text-black px-3 py-1 rounded-full shrink-0">
                        <span className="font-['JetBrains_Mono'] text-[10px] tracking-widest font-bold">AGENT-02</span>
                      </div>
                    </div>
                    <p className="font-['DM_Sans'] text-[15px] text-white/70 leading-[1.6] font-light">{msg.text}</p>
                    <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center justify-end gap-6">
                      <span>MODEL: {msg.model}</span>
                      <span>LATENCY: {msg.latency}ms</span>
                    </div>
                  </motion.div>
                );
              }
              if (msg.type === 'verdict') {
                return (
                  <motion.div key={idx} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }} className="flex justify-center will-change-[transform,opacity] transform-gpu">
                    <div className="bg-indigo-500/[0.06] border border-indigo-500/20 rounded-2xl p-6 max-w-lg w-full text-center">
                      <div className="font-['JetBrains_Mono'] text-[10px] text-indigo-400 tracking-widest uppercase mb-4 font-bold flex items-center justify-center gap-2">
                        <Gavel className="w-3.5 h-3.5" />ROUND {msg.round} VERDICT
                      </div>
                      <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="bg-white/[0.03] rounded-xl p-3">
                          <div className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest mb-1">PRO SCORE</div>
                          <div className="text-2xl font-['DM_Sans'] text-white font-semibold">{msg.data.pro_scores.total}<span className="text-sm text-white/30">/10</span></div>
                        </div>
                        <div className="bg-white/[0.03] rounded-xl p-3">
                          <div className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest mb-1">CON SCORE</div>
                          <div className="text-2xl font-['DM_Sans'] text-white font-semibold">{msg.data.con_scores.total}<span className="text-sm text-white/30">/10</span></div>
                        </div>
                      </div>
                      <div className="font-['JetBrains_Mono'] text-[10px] text-white/60 tracking-widest uppercase mb-2">WINNER: <span className="text-white font-bold">{msg.data.round_winner.toUpperCase()}</span></div>
                      <p className="font-['DM_Sans'] text-sm text-white/50 leading-relaxed">{asText(msg.data.reasoning)}</p>
                    </div>
                  </motion.div>
                );
              }
              if (msg.type === 'final_verdict') {
                const winner = msg.data.overall_winner as 'pro' | 'con' | 'tie';
                const proTotal = msg.data.pro_total as number;
                const conTotal = msg.data.con_total as number;

                const winnerConfig = {
                  pro: {
                    label: 'AGENT-01 // PRO WINS',
                    color: 'text-emerald-400',
                    border: 'border-emerald-500/30',
                    bg: 'bg-emerald-500/[0.06]',
                    glow: 'shadow-[0_0_30px_rgba(52,211,153,0.08)]',
                  },
                  con: {
                    label: 'AGENT-02 // CON WINS',
                    color: 'text-rose-400',
                    border: 'border-rose-500/30',
                    bg: 'bg-rose-500/[0.06]',
                    glow: 'shadow-[0_0_30px_rgba(251,113,133,0.08)]',
                  },
                  tie: {
                    label: 'DRAW // TIE',
                    color: 'text-yellow-400',
                    border: 'border-yellow-500/30',
                    bg: 'bg-yellow-500/[0.04]',
                    glow: 'shadow-[0_0_30px_rgba(250,204,21,0.06)]',
                  },
                }[winner];

                const d = msg.data;
                const winnerAnalysis = d.winner ?? {};
                const loserAnalysis = d.loser ?? {};
                const accuracy = d.accuracy ?? { pro: 0, con: 0 };
                const winnerPoints: string[] = (winnerAnalysis.points ?? winnerAnalysis.strengths ?? []).map(asText);
                const fallacies: string[] = (d.fallacies ?? []).map(asText);
                const verdictText: string = asText(d.verdict ?? d.final_reasoning);
                // support both old field name (missed_opportunities) and new (missed_points)
                const loserMissed: string[] = (loserAnalysis.missed_points ?? loserAnalysis.missed_opportunities ?? []).map(asText);
                const rounds: any[] = d.rounds ?? messages
                  .filter((m: any) => m.type === 'verdict')
                  .map((rv: any) => ({
                    r: rv.round,
                    winner: rv.data.round_winner,
                    margin: Math.abs(rv.data.pro_scores.total - rv.data.con_scores.total).toFixed(1),
                    swing: rv.data.reasoning,
                  }));

                return (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, scale: 0.97, y: 20 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="flex justify-center will-change-[transform,opacity] transform-gpu"
                  >
                    <div className={`bg-[#111114] border border-white/10 rounded-3xl px-8 py-7 sm:px-9 max-w-2xl w-full ${winnerConfig.glow}`}>

                      {/* Presentation notes:

                          Sections animate in on a stagger rather than appearing
                          at once. A verdict arrives after minutes of waiting, so
                          revealing it in reading order gives the result a beat
                          instead of dumping a wall of text.

                          Scores share one proportional bar rather than two
                          independent ones. Two bars ask the reader to compare
                          lengths across a gap; one split bar makes the margin
                          the thing you see first.

                          Colour is carried by the two agents only — emerald and
                          rose — and used nowhere else, so it always means
                          "which side" and never decoration. */}

                      {(() => {
                        const R = d.receipts;
                        const NAMES: Record<string, string> = {
                          evidence: 'Evidence cited',
                          logic: 'Reasoning',
                          relevance: 'Stayed on topic',
                        };
                        let step = 0;
                        const rise = () => ({
                          initial: { opacity: 0, y: 12 },
                          animate: { opacity: 1, y: 0 },
                          transition: { duration: 0.45, delay: 0.08 * step++, ease: [0.16, 1, 0.3, 1] as const },
                        });
                        const Rule = () => <div className="h-px bg-white/[0.06]" />;
                        const Label = ({ children, tone }: { children: React.ReactNode; tone?: string }) => (
                          <div className={cn(
                            "font-['DM_Sans'] text-[11px] font-semibold tracking-[0.12em] uppercase mb-3",
                            tone ?? "text-white/40")}>{children}</div>
                        );
                        const total = Math.max(1, proTotal + conTotal);
                        const proShare = (proTotal / total) * 100;

                        return (
                          <>
                            {/* The hero carries the result. Everything sat
                                within a narrow type range before — a 15px
                                header, a 34px name, 26px scores — so nothing
                                led. The winner is now the largest thing on the
                                screen by a wide margin, the kicker is small and
                                letterspaced so it reads as a caption rather
                                than a competing heading, and a soft radial wash
                                in the winning side's colour gives the block
                                depth without adding a border. */}
                            <div className="relative">
                              <div
                                aria-hidden
                                className="pointer-events-none absolute inset-x-0 -top-10 h-64 opacity-[0.22]"
                                style={{
                                  background: `radial-gradient(ellipse 60% 55% at 50% 0%, ${
                                    winner === 'pro' ? 'rgb(52,211,153)' : winner === 'con' ? 'rgb(251,113,133)' : 'rgb(148,163,184)'
                                  }, transparent 70%)`,
                                }}
                              />

                              <motion.div {...rise()} className="relative text-center pt-2">
                                <div className="font-['JetBrains_Mono'] text-[10px] tracking-[0.3em] uppercase text-white/30 mb-5">
                                  Final Verdict
                                </div>

                                <div className={cn(
                                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full mb-5",
                                  winner === 'tie' ? "bg-white/[0.07]"
                                    : winner === 'pro' ? "bg-emerald-400/15" : "bg-rose-400/15")}>
                                  <span className={cn("w-1 h-1 rounded-full",
                                    winner === 'tie' ? "bg-white/50" : winner === 'pro' ? "bg-emerald-400" : "bg-rose-400")} />
                                  <span className={cn("font-['DM_Sans'] text-[10px] font-bold tracking-[0.14em] uppercase",
                                    winner === 'tie' ? "text-white/55" : winner === 'pro' ? "text-emerald-300" : "text-rose-300")}>
                                    {winner === 'tie' ? 'Draw' : 'Winner'}
                                  </span>
                                </div>

                                <div className={cn(
                                  "font-['Orbitron'] font-black tracking-[0.02em] leading-[1.05] mb-6 uppercase",
                                  winner === 'tie' ? "text-[24px] text-white/85" : "text-[34px]",
                                  winner === 'pro' && "text-emerald-400",
                                  winner === 'con' && "text-rose-400")}>
                                  {winner === 'tie' ? 'Too close to separate' : winner === 'pro' ? 'Agent 01' : 'Agent 02'}
                                </div>

                                {winnerAnalysis.decisive_argument && (
                                  <p className="font-['DM_Sans'] text-[14px] text-white/55 leading-[1.6] max-w-[28rem] mx-auto">
                                    {asText(winnerAnalysis.decisive_argument)}
                                  </p>
                                )}
                              </motion.div>
                            </div>

                            {/* Scores. The numbers are the anchor, so labels and
                                percentages sit well below them in the hierarchy
                                rather than competing at a similar size. */}
                            <motion.div {...rise()} className="pt-6 pb-5">
                              <div className="flex items-end justify-between mb-4">
                                <div>
                                  <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.14em] uppercase text-emerald-400/60 mb-2">
                                    Agent 01
                                  </div>
                                  <div className="font-['Orbitron'] text-[27px] leading-[0.95] font-bold text-white tracking-[0.01em]">
                                    {proTotal}
                                  </div>
                                </div>

                                <div className="pb-1.5 text-center">
                                  <div className="font-['JetBrains_Mono'] text-[10px] tracking-[0.2em] uppercase text-white/20">
                                    out of 30
                                  </div>
                                </div>

                                <div className="text-right">
                                  <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.14em] uppercase text-rose-400/60 mb-2">
                                    Agent 02
                                  </div>
                                  <div className="font-['Orbitron'] text-[27px] leading-[0.95] font-bold text-white tracking-[0.01em]">
                                    {conTotal}
                                  </div>
                                </div>
                              </div>

                              <div className="flex h-[5px] rounded-full overflow-hidden bg-white/[0.05] gap-[2px]">
                                <motion.div
                                  className="bg-emerald-400 rounded-full"
                                  initial={{ width: '50%' }}
                                  animate={{ width: `${proShare}%` }}
                                  transition={{ duration: 1, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
                                />
                                <div className="flex-1 bg-rose-400 rounded-full" />
                              </div>

                              <div className="flex justify-between mt-3">
                                <span className="font-['DM_Sans'] text-[11px] text-white/30 tracking-wide">
                                  {accuracy.pro.toFixed(0)}% of available
                                </span>
                                <span className="font-['DM_Sans'] text-[11px] text-white/30 tracking-wide">
                                  {accuracy.con.toFixed(0)}% of available
                                </span>
                              </div>
                            </motion.div>

                            {/* Why each side scored what it did */}
                            {(d.score_explanation?.pro || d.score_explanation?.con) && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-5 grid sm:grid-cols-2 gap-4">
                                  {([['pro', d.score_explanation?.pro], ['con', d.score_explanation?.con]] as const).map(([side, why]) =>
                                    why ? (
                                      <div key={side} className="rounded-2xl bg-white/[0.025] p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                          <span className={cn("w-1.5 h-1.5 rounded-full", side === 'pro' ? "bg-emerald-400" : "bg-rose-400")} />
                                          <span className="font-['DM_Sans'] text-[12px] font-semibold text-white/75">
                                            {side === 'pro' ? 'Agent 01' : 'Agent 02'}
                                          </span>
                                        </div>
                                        <p className="font-['DM_Sans'] text-[12.5px] text-white/60 leading-relaxed">{asText(why)}</p>
                                      </div>
                                    ) : null)}
                                </motion.div>
                              </>
                            )}

                            {/* The judge's call */}
                            {verdictText && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-5">
                                  <Label>The judge's call</Label>
                                  <div className="rounded-2xl bg-white/[0.025] p-4">
                                    <p className="font-['DM_Sans'] text-[14px] text-white/75 leading-[1.75]">{verdictText}</p>
                                  </div>
                                </motion.div>
                              </>
                            )}

                            {/* Confidence */}
                            {d.confidence?.available && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className={cn(
                                  "my-5 rounded-2xl px-4 py-3.5 flex items-start gap-3 border",
                                  d.confidence.abstain ? "border-amber-400/20 bg-amber-400/[0.04]" : "border-emerald-400/20 bg-emerald-400/[0.04]")}>
                                  <span className={cn("mt-[7px] w-1.5 h-1.5 rounded-full shrink-0",
                                    d.confidence.abstain ? "bg-amber-400" : "bg-emerald-400")} />
                                  <div>
                                    <div className="font-['DM_Sans'] text-[13px] font-semibold text-white/85 mb-1">
                                      {d.confidence.abstain ? 'Too close to call with confidence' : 'A clear result'}
                                    </div>
                                    <p className="font-['DM_Sans'] text-[12px] text-white/55 leading-relaxed">
                                      {d.confidence.abstain
                                        ? 'The scores are close enough that this outcome is not reliable on its own.'
                                        : `Measured against ${d.confidence.n_calibration} debates judged by people, a result this decisive holds at least ${Math.round((1 - d.confidence.alpha) * 100)}% of the time.`}
                                    </p>
                                  </div>
                                </motion.div>
                              </>
                            )}

                            {/* Why this verdict */}
                            {R?.criteria && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-5">
                                  <Label>Why this verdict</Label>

                                  <div className="mb-8">
                                    {(['evidence', 'logic', 'relevance'] as const).map((c, i) => {
                                      const pro = R.criteria.pro[c];
                                      const con = R.criteria.con[c];
                                      const sum = Math.max(0.001, pro + con);
                                      const decisive = R.decisive_criterion === c;
                                      return (
                                        <div key={c} className="mb-5 last:mb-0">
                                          <div className="flex items-baseline justify-between mb-2">
                                            <span className="font-['DM_Sans'] text-[13px] text-white/75">
                                              {NAMES[c]}
                                              {decisive && (
                                                <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide uppercase bg-white/[0.07] text-white/50">
                                                  decisive
                                                </span>
                                              )}
                                            </span>
                                            <span className="font-['JetBrains_Mono'] text-[12px]">
                                              <span className="text-emerald-400/80">{pro}</span>
                                              <span className="text-white/20 mx-1.5">·</span>
                                              <span className="text-rose-400/80">{con}</span>
                                            </span>
                                          </div>
                                          <div className="flex h-1 rounded-full overflow-hidden bg-white/[0.06]">
                                            <motion.div
                                              className="bg-emerald-400/70"
                                              initial={{ width: '50%' }}
                                              animate={{ width: `${(pro / sum) * 100}%` }}
                                              transition={{ duration: 0.7, delay: 0.4 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                                            />
                                            <div className="flex-1 bg-rose-400/70" />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>

                                  {R.verification && (
                                    <div className="grid sm:grid-cols-2 gap-4">
                                      {(['pro', 'con'] as const).map((side) => {
                                        const v = R.verification[side];
                                        const cited = R.cited?.[side] ?? [];
                                        return (
                                          <div key={side} className="rounded-2xl bg-white/[0.025] p-4">
                                            <div className="flex items-center justify-between mb-3">
                                              <div className="flex items-center gap-2">
                                                <span className={cn("w-1.5 h-1.5 rounded-full", side === 'pro' ? "bg-emerald-400" : "bg-rose-400")} />
                                                <span className="font-['DM_Sans'] text-[12px] font-semibold text-white/75">
                                                  {side === 'pro' ? 'Agent 01' : 'Agent 02'}
                                                </span>
                                              </div>
                                              <span className="font-['JetBrains_Mono'] text-[11px] text-white/40">
                                                {v.supported}/{v.claims_checked} verified
                                              </span>
                                            </div>
                                            {v.refuted > 0 && (
                                              <div className="font-['DM_Sans'] text-[11px] text-amber-400/80 mb-2">
                                                {v.refuted} claim{v.refuted > 1 ? 's' : ''} contradicted by sources
                                              </div>
                                            )}
                                            {cited.slice(0, 3).map((e: any, k: number) => (
                                              <p key={k} className="font-['DM_Sans'] text-[12.5px] text-white/60 leading-relaxed mb-2 last:mb-0">
                                                {asText(e)}
                                              </p>
                                            ))}
                                            {cited.length === 0 && (
                                              <p className="font-['DM_Sans'] text-[12.5px] text-white/30 italic">Nothing checkable was cited.</p>
                                            )}
                                            {cited.length > 3 && (
                                              <p className="font-['DM_Sans'] text-[11px] text-white/30 mt-2">and {cited.length - 3} more</p>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </motion.div>
                              </>
                            )}

                            {/* What won it / what lost it */}
                            {(winnerPoints.length > 0 || loserAnalysis.fatal_weakness || loserMissed.length > 0) && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-7 grid sm:grid-cols-2 gap-x-8 gap-y-6">
                                  {winnerPoints.length > 0 && (
                                    <div>
                                      <Label tone="text-emerald-400/70">What won it</Label>
                                      <div className="rounded-2xl bg-white/[0.025] p-4">
                                        {winnerPoints.map((sPt: string, i: number) => (
                                          <div key={i} className="flex gap-2.5 mb-2 last:mb-0">
                                            <span className="bg-emerald-400/50 mt-[7px] w-1 h-1 rounded-full shrink-0" />
                                            <p className="font-['DM_Sans'] text-[12.5px] text-white/65 leading-relaxed">{sPt}</p>
                                          </div>
                                        ))}
                                        {winnerAnalysis.strongest_round && (
                                          <p className="font-['DM_Sans'] text-[11px] text-white/30 mt-3 pt-3 border-t border-white/[0.05]">
                                            Strongest in round {winnerAnalysis.strongest_round}
                                          </p>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  {(loserAnalysis.fatal_weakness || loserMissed.length > 0) && (
                                    <div>
                                      <Label tone="text-rose-400/70">What lost it</Label>
                                      <div className="rounded-2xl bg-white/[0.025] p-4">
                                        {loserAnalysis.fatal_weakness && (
                                          <div className="flex gap-2.5 mb-2 last:mb-0">
                                            <span className="bg-rose-400/50 mt-[7px] w-1 h-1 rounded-full shrink-0" />
                                            <p className="font-['DM_Sans'] text-[12.5px] text-white/65 leading-relaxed">{asText(loserAnalysis.fatal_weakness)}</p>
                                          </div>
                                        )}
                                        {loserMissed.map((m: string, i: number) => (
                                          <div key={i} className="flex gap-2.5 mb-2 last:mb-0">
                                            <span className="bg-white/20 mt-[7px] w-1 h-1 rounded-full shrink-0" />
                                            <p className="font-['DM_Sans'] text-[12.5px] text-white/50 leading-relaxed">{m}</p>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </motion.div>
                              </>
                            )}

                            {/* Round by round */}
                            {rounds.length > 0 && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-5">
                                  <Label>Round by round</Label>
                                  <div className="rounded-2xl bg-white/[0.025] px-4 py-1">
                                  {rounds.map((rv: any, i: number) => (
                                    <div key={i} className="flex items-baseline gap-3.5 py-3 border-b border-white/[0.05] last:border-0">
                                      <span className="font-['JetBrains_Mono'] text-[11px] text-white/30 w-6 shrink-0">R{rv.r}</span>
                                      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0 translate-y-[-1px]",
                                        rv.winner === 'pro' ? "bg-emerald-400" : rv.winner === 'con' ? "bg-rose-400" : "bg-white/30")} />
                                      <span className={cn("font-['DM_Sans'] text-[13px] font-semibold w-[62px] shrink-0",
                                        rv.winner === 'pro' && 'text-emerald-400/90',
                                        rv.winner === 'con' && 'text-rose-400/90',
                                        rv.winner === 'tie' && 'text-white/50')}>
                                        {rv.winner === 'tie' ? 'Draw' : rv.winner === 'pro' ? 'Agent 01' : 'Agent 02'}
                                      </span>
                                      <span className="font-['JetBrains_Mono'] text-[11px] text-white/30 w-10 shrink-0">
                                        +{typeof rv.margin === 'number' ? rv.margin.toFixed(1) : rv.margin}
                                      </span>
                                      <span className="font-['DM_Sans'] text-[12.5px] text-white/60 leading-snug">{asText(rv.swing)}</span>
                                    </div>
                                  ))}
                                  </div>
                                </motion.div>
                              </>
                            )}

                            {/* Reasoning errors */}
                            {fallacies.length > 0 && (
                              <>
                                <Rule />
                                <motion.div {...rise()} className="py-5">
                                  <Label tone="text-amber-400/70">Reasoning errors flagged</Label>
                                  <div className="rounded-2xl bg-amber-400/[0.04] border border-amber-400/15 p-4">
                                    {fallacies.map((f: string, i: number) => (
                                      <p key={i} className="font-['DM_Sans'] text-[12.5px] text-white/65 leading-relaxed mb-1.5 last:mb-0">{f}</p>
                                    ))}
                                  </div>
                                </motion.div>
                              </>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </motion.div>
                );
              }

              return null;
            })}

            {/* A rate-limit wait can last minutes. Showing it is the difference
                between "the system is waiting" and "the button is broken". */}
            {notice && !error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center">
                <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-full border border-amber-400/20 bg-amber-400/[0.05]">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shrink-0" />
                  <span className="font-['DM_Sans'] text-[12px] text-amber-200/80">{notice}</span>
                </div>
              </motion.div>
            )}

            {typingAgent && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={cn("flex items-center gap-3 py-4", typingAgent === 'con' ? "self-end" : "")}>
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase">
                  {typingAgent === 'pro' ? 'AGENT-01' : typingAgent === 'con' ? 'AGENT-02' : 'JUDGE-0 OMNI'} {typingAgent === 'judge' ? 'evaluating' : 'generating'}...
                </span>
              </motion.div>
            )}



            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center">
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-6 py-4 text-center max-w-md">
                  <span className="font-['JetBrains_Mono'] text-xs text-red-400 tracking-widest">{error}</span>
                </div>
              </motion.div>
            )}

            {debateComplete && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-3">
                <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest uppercase flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-500" />DEBATE PROTOCOL COMPLETE
                </div>
                <div className="flex items-center gap-3 flex-wrap justify-center">
                  <button
                    onClick={handleExportPdf}
                    disabled={isExportingPdf}
                    className="flex items-center gap-2 px-6 py-3 rounded-full border border-emerald-500/40 hover:border-emerald-500/70 bg-emerald-500/[0.08] hover:bg-emerald-500/[0.16] text-emerald-300 transition-all cursor-pointer shadow-[0_0_20px_rgba(52,211,153,0.12)] active:scale-95 disabled:opacity-50"
                  >
                    {isExportingPdf ? (
                      <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                    ) : pdfExported ? (
                      <Check className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <FileDown className="w-4 h-4 text-emerald-400" />
                    )}
                    <span className="font-['JetBrains_Mono'] text-[11px] tracking-widest uppercase font-bold">
                      {isExportingPdf
                        ? 'GENERATING PDF…'
                        : pdfExported === 'downloaded'
                        ? 'PDF DOWNLOADED!'
                        : 'EXPORT DEBATE (PDF)'}
                    </span>
                  </button>
                </div>
              </motion.div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}

        {/* Input Bar */}
        <div className="absolute bottom-0 left-0 right-0 p-6 md:p-12 flex flex-col items-center z-10 bg-gradient-to-t from-[#0a0a0c] via-[#0a0a0c] to-transparent pt-20 gap-3">

          {/* Human argument panel — shown when it's the user's turn */}
          <AnimatePresence>
            {humanTurn && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 16 }}
                className="w-full max-w-4xl"
              >
                <div className={cn(
                  "rounded-2xl border p-4 mb-2",
                  humanTurn.role === 'pro'
                    ? 'bg-emerald-500/[0.06] border-emerald-500/25'
                    : 'bg-rose-500/[0.06] border-rose-500/25'
                )}>
                  <div className="flex items-center justify-between mb-3">
                    <span className={cn(
                      "font-['JetBrains_Mono'] text-[10px] tracking-widest uppercase font-bold",
                      humanTurn.role === 'pro' ? 'text-emerald-400' : 'text-rose-400'
                    )}>
                      🎤 Your turn — {humanTurn.role.toUpperCase()} · R{humanTurn.round} · {humanTurn.sub_round === 1 ? 'Opening' : humanTurn.sub_round === 2 ? 'Rebuttal' : 'Justify'}
                    </span>
                    <span className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest">
                      {humanInput.trim().split(/\s+/).filter(Boolean).length} words
                    </span>
                  </div>
                  <textarea
                    autoFocus
                    value={humanInput}
                    onChange={e => setHumanInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendHumanArgument(); }}
                    placeholder="Type your argument… (Ctrl+Enter to submit)"
                    rows={4}
                    className="w-full bg-transparent border-none outline-none text-white/80 font-['DM_Sans'] text-sm leading-relaxed placeholder:text-white/20 resize-none"
                  />
                  <div className="flex justify-end mt-2">
                    <button
                      onClick={sendHumanArgument}
                      disabled={!humanInput.trim()}
                      className={cn(
                        "px-5 py-2.5 rounded-full font-['JetBrains_Mono'] text-[10px] font-bold tracking-widest uppercase transition-all",
                        humanInput.trim()
                          ? 'bg-white text-black hover:bg-white/90 active:scale-95'
                          : 'bg-white/10 text-white/30 cursor-not-allowed'
                      )}
                    >
                      Submit argument →
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Normal debate topic input */}
          {!humanTurn && (
            <form onSubmit={handleStartDebate} className="w-full max-w-4xl bg-[#161618] rounded-full p-2 pl-6 flex items-center border border-white/[0.05]">
              <div className="flex items-center justify-center shrink-0 mr-4"><Zap className="w-5 h-5 text-white" /></div>
              <input type="text" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="ENTER DEBATE TOPIC..." className="flex-1 bg-transparent border-none outline-none text-white/80 font-['JetBrains_Mono'] text-xs tracking-widest placeholder:text-white/30 font-semibold" />
              <button type="submit" disabled={!!typingAgent || !prompt.trim()} className="bg-white text-black px-6 py-3.5 rounded-full flex items-center gap-2 hover:bg-white/90 transition-transform active:scale-95 shrink-0 ml-2 disabled:opacity-50 disabled:cursor-not-allowed">
                <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">{typingAgent ? 'Debating...' : 'Start Debate'}</span>
                <span className="text-[#facc15]">{'\u26A1'}</span>
              </button>
            </form>
          )}
        </div>

      </main>
    </div>
  );
}