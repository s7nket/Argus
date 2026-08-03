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
  ArrowLeft
} from 'lucide-react';
import { cn } from '../lib/utils';
import { api, wsUrl } from '../lib/api';
import { useNavigate } from 'react-router';

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
  const rounds = 3;
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const typingStartRef = useRef<number>(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const judgeFailuresRef = useRef(0);
  const debateCompleteRef = useRef(false);
  const errorOccurredRef = useRef(false);

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
    if (!prompt.trim() || typingAgent) return;

    if (judgeStatus === 'offline') {
      setError('Judge is offline. Start your Kaggle FT scorer (FT_JUDGE_URL) and set JUDGE_GROQ_API_KEY in backend/.env.');
      return;
    }
    setIsDebating(true);
    setMessages([]);
    setTypingAgent(null);
    setDebateComplete(false);
    debateCompleteRef.current = false;
    errorOccurredRef.current = false;
    setError(null);

    const ws = new WebSocket(wsUrl('/ws/debate'));
    wsRef.current = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ topic: prompt, rounds }));
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
          debateCompleteRef.current = true;
          setDebateComplete(true);
          setTypingAgent(null);
          break;
        case 'error':
          errorOccurredRef.current = true;
          setError(msg.message);
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
  }, [prompt, rounds, typingAgent, judgeStatus]);

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
                <h2 className="font-['Orbitron'] text-lg text-white/90 mb-1">{asText(openDebate.topic)}</h2>
                <p className="font-['JetBrains_Mono'] text-[10px] text-white/35 tracking-widest uppercase mb-6">
                  {new Date(openDebate.created_at).toLocaleString()} · {(openDebate.rounds ?? []).length} rounds
                </p>
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
              <p className="font-['DM_Sans'] text-sm text-white/30 leading-relaxed font-medium mb-10">Enter a debate topic below to engage neural simulation protocols and deploy active agents.</p>
              
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
          <div className="flex-1 overflow-y-auto px-6 md:px-20 lg:px-40 pt-48 pb-48 flex flex-col gap-10 scroll-smooth z-0">
            {messages.map((msg, idx) => {
              if (msg.type === 'sub_round_divider') {
                const subColors: Record<number, string> = { 1: 'text-sky-400/70 border-sky-500/20', 2: 'text-amber-400/70 border-amber-500/20', 3: 'text-violet-400/70 border-violet-500/20' };
                const colorClass = subColors[msg.sub_round] ?? 'text-white/40 border-white/10';
                return (
                  <motion.div key={idx} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-4 my-2">
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
                  <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-col gap-4 max-w-3xl will-change-[transform,opacity] transform-gpu">
                    <div className="flex items-center gap-3 w-full">
                      <div className="bg-white/10 px-3 py-1 rounded-full border border-white/10 shrink-0">
                        <span className="font-['JetBrains_Mono'] text-[10px] text-white tracking-widest font-bold">AGENT-01</span>
                      </div>
                      <span className="font-['JetBrains_Mono'] text-[9px] text-white/30 tracking-widest uppercase">{msg.model}</span>
                      <div className="h-[1px] bg-white/[0.05] flex-1" />
                      <span className="font-['JetBrains_Mono'] text-[10px] text-emerald-400/80 tracking-widest font-bold">PRO</span>
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest">R{msg.round}</span>
                    </div>
                    <p className="font-['DM_Sans'] text-base md:text-lg text-white/80 leading-relaxed font-light">{msg.text}</p>
                    <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center gap-6 mt-1">
                      <span>MODEL: {msg.model}</span>
                      <span>LATENCY: {msg.latency}ms</span>
                    </div>
                  </motion.div>
                );
              }
              if (msg.type === 'con') {
                return (
                  <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-col gap-4 max-w-3xl self-end text-left will-change-[transform,opacity] transform-gpu">
                    <div className="flex items-center gap-3 w-full justify-end">
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest">R{msg.round}</span>
                      <span className="font-['JetBrains_Mono'] text-[10px] text-rose-400/80 tracking-widest font-bold">CON</span>
                      <div className="h-[1px] bg-white/[0.05] flex-1" />
                      <span className="font-['JetBrains_Mono'] text-[9px] text-white/30 tracking-widest uppercase">{msg.model}</span>
                      <div className="bg-white text-black px-3 py-1 rounded-full shrink-0">
                        <span className="font-['JetBrains_Mono'] text-[10px] tracking-widest font-bold">AGENT-02</span>
                      </div>
                    </div>
                    <p className="font-['DM_Sans'] text-base md:text-lg text-white/70 leading-relaxed font-light">{msg.text}</p>
                    <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center justify-end gap-6 mt-1">
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
                    <div className={`bg-[#111114] border border-white/10 rounded-3xl p-8 max-w-2xl w-full ${winnerConfig.glow}`}>

                      {/* One type scale for the whole card. Section labels
                          were a mix of Orbitron, JetBrains Mono and DM Sans at
                          several weights, and body copy sat at white/35-white/45
                          — present, but not readably so. Labels are uniform now
                          and body copy is white/65 or brighter. Hairlines divide
                          sections instead of nesting each one in its own
                          bordered card.

                          Removed: scorer name, verifier backend and position-bias
                          figure. Those describe how the system was built, not why
                          this side won, and they belong in JUDGE LOGS. */}

                      <div className="flex items-center gap-3 mb-7">
                        <div className="w-9 h-9 rounded-full bg-white/[0.06] flex items-center justify-center text-white/70">
                          <Gavel className="w-4 h-4" />
                        </div>
                        <span className="font-['DM_Sans'] text-[15px] font-semibold text-white tracking-tight">Final Verdict</span>
                      </div>

                      <div className="text-center pb-7">
                        <div className={cn("font-['DM_Sans'] text-[32px] leading-none font-semibold tracking-tight mb-3", winnerConfig.color)}>
                          {winner === 'tie' ? 'Draw' : winner === 'pro' ? 'Agent 01 wins' : 'Agent 02 wins'}
                        </div>
                        <div className="font-['JetBrains_Mono'] text-sm text-white/45">
                          {proTotal} <span className="text-white/20">—</span> {conTotal}
                        </div>
                        {winnerAnalysis.decisive_argument && (
                          <p className="font-['DM_Sans'] text-[15px] text-white/70 leading-relaxed mt-5 max-w-lg mx-auto">
                            {asText(winnerAnalysis.decisive_argument)}
                          </p>
                        )}
                      </div>

                      <div className="h-px bg-white/[0.07]" />

                      {verdictText && (
                        <>
                          <div className="py-7">
                            <p className="font-['DM_Sans'] text-[15px] text-white/80 leading-[1.7]">{verdictText}</p>
                          </div>
                          <div className="h-px bg-white/[0.07]" />
                        </>
                      )}

                      {/* Confidence, said in words. The coverage guarantee is
                          the point; alpha and calibration size are not. */}
                      {d.confidence?.available && (
                        <>
                          <div className="py-7 flex items-start gap-3">
                            <span className={cn("mt-[7px] w-1.5 h-1.5 rounded-full shrink-0",
                              d.confidence.abstain ? "bg-amber-400" : "bg-emerald-400")} />
                            <div>
                              <div className="font-['DM_Sans'] text-sm font-semibold text-white/85 mb-1">
                                {d.confidence.abstain ? 'Too close to call with confidence' : 'A clear result'}
                              </div>
                              <p className="font-['DM_Sans'] text-[13px] text-white/55 leading-relaxed">
                                {d.confidence.abstain
                                  ? 'The scores are close enough that this outcome is not reliable on its own.'
                                  : `Measured against ${d.confidence.n_calibration} debates judged by people, a result this decisive holds at least ${Math.round((1 - d.confidence.alpha) * 100)}% of the time.`}
                              </p>
                            </div>
                          </div>
                          <div className="h-px bg-white/[0.07]" />
                        </>
                      )}

                      {d.receipts?.criteria && (() => {
                        const R = d.receipts;
                        const NAMES: Record<string, string> = {
                          evidence: 'Evidence cited',
                          logic: 'Reasoning',
                          relevance: 'Stayed on topic',
                        };
                        return (
                          <div className="py-7">
                            <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.12em] uppercase text-white/40 mb-5">
                              Why this verdict
                            </div>

                            <div className="mb-7">
                              {(['evidence', 'logic', 'relevance'] as const).map((c) => {
                                const pro = R.criteria.pro[c];
                                const con = R.criteria.con[c];
                                const decisive = R.decisive_criterion === c;
                                return (
                                  <div key={c} className="mb-4 last:mb-0">
                                    <div className="flex items-baseline justify-between mb-2">
                                      <span className="font-['DM_Sans'] text-[13px] text-white/70">
                                        {NAMES[c]}
                                        {decisive && <span className="text-white/35 ml-2">decided it</span>}
                                      </span>
                                      <span className="font-['JetBrains_Mono'] text-[12px] text-white/50">
                                        {pro} <span className="text-white/20">vs</span> {con}
                                      </span>
                                    </div>
                                    <div className="flex gap-1">
                                      <div className="flex-1 h-1 rounded-full bg-white/[0.07] overflow-hidden">
                                        <div className="h-full bg-emerald-400/80 rounded-full" style={{ width: `${Math.min(100, pro * 10)}%` }} />
                                      </div>
                                      <div className="flex-1 h-1 rounded-full bg-white/[0.07] overflow-hidden">
                                        <div className="h-full bg-rose-400/80 rounded-full" style={{ width: `${Math.min(100, con * 10)}%` }} />
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>

                            {R.verification && (
                              <div className="grid sm:grid-cols-2 gap-x-8 gap-y-6">
                                {(['pro', 'con'] as const).map((side) => {
                                  const v = R.verification[side];
                                  const cited = R.cited?.[side] ?? [];
                                  return (
                                    <div key={side}>
                                      <div className="flex items-center gap-2 mb-2">
                                        <span className={cn("w-1.5 h-1.5 rounded-full", side === 'pro' ? "bg-emerald-400" : "bg-rose-400")} />
                                        <span className="font-['DM_Sans'] text-[13px] font-semibold text-white/75">
                                          {side === 'pro' ? 'Agent 01' : 'Agent 02'}
                                        </span>
                                      </div>
                                      <p className="font-['DM_Sans'] text-[12px] text-white/45 mb-3">
                                        {v.supported} of {v.claims_checked} claims confirmed against sources
                                        {v.refuted > 0 && <span className="text-amber-400/80"> · {v.refuted} contradicted</span>}
                                      </p>
                                      {cited.slice(0, 3).map((e: any, k: number) => (
                                        <p key={k} className="font-['DM_Sans'] text-[13px] text-white/65 leading-relaxed mb-2">
                                          {asText(e)}
                                        </p>
                                      ))}
                                      {cited.length === 0 && (
                                        <p className="font-['DM_Sans'] text-[13px] text-white/35">Cited nothing that could be checked.</p>
                                      )}
                                      {cited.length > 3 && (
                                        <p className="font-['DM_Sans'] text-[12px] text-white/30">and {cited.length - 3} more</p>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      {(loserAnalysis.fatal_weakness || loserMissed.length > 0) && (
                        <>
                          <div className="h-px bg-white/[0.07]" />
                          <div className="py-7">
                            <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.12em] uppercase text-white/40 mb-4">
                              What the losing side missed
                            </div>
                            {loserAnalysis.fatal_weakness && (
                              <p className="font-['DM_Sans'] text-[14px] text-white/75 leading-relaxed mb-3">
                                {asText(loserAnalysis.fatal_weakness)}
                              </p>
                            )}
                            {loserMissed.map((m: string, i: number) => (
                              <p key={i} className="font-['DM_Sans'] text-[13px] text-white/55 leading-relaxed mb-1.5">{m}</p>
                            ))}
                          </div>
                        </>
                      )}

                      {rounds.length > 0 && (
                        <>
                          <div className="h-px bg-white/[0.07]" />
                          <div className="py-7">
                            <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.12em] uppercase text-white/40 mb-4">
                              Round by round
                            </div>
                            {rounds.map((rv: any, i: number) => (
                              <div key={i} className="flex items-baseline gap-4 py-2.5 border-b border-white/[0.05] last:border-0">
                                <span className="font-['JetBrains_Mono'] text-[12px] text-white/35 w-7 shrink-0">R{rv.r}</span>
                                <span className={cn("font-['DM_Sans'] text-[13px] font-semibold w-[70px] shrink-0",
                                  rv.winner === 'pro' && 'text-emerald-400/90',
                                  rv.winner === 'con' && 'text-rose-400/90',
                                  rv.winner === 'tie' && 'text-white/50')}>
                                  {rv.winner === 'tie' ? 'Draw' : rv.winner === 'pro' ? 'Agent 01' : 'Agent 02'}
                                </span>
                                <span className="font-['DM_Sans'] text-[13px] text-white/60 leading-snug">{asText(rv.swing)}</span>
                              </div>
                            ))}
                          </div>
                        </>
                      )}

                      {fallacies.length > 0 && (
                        <>
                          <div className="h-px bg-white/[0.07]" />
                          <div className="py-7">
                            <div className="font-['DM_Sans'] text-[11px] font-semibold tracking-[0.12em] uppercase text-amber-400/70 mb-3">
                              Reasoning errors flagged
                            </div>
                            {fallacies.map((f: string, i: number) => (
                              <p key={i} className="font-['DM_Sans'] text-[13px] text-white/65 leading-relaxed mb-1.5">{f}</p>
                            ))}
                          </div>
                        </>
                      )}

                    </div>
                  </motion.div>
                );
              }

              return null;
            })}

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
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center">
                <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest uppercase flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-500" />DEBATE PROTOCOL COMPLETE
                </div>
              </motion.div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}

        {/* Input Bar */}
        <div className="absolute bottom-0 left-0 right-0 p-6 md:p-12 flex justify-center z-10 bg-gradient-to-t from-[#0a0a0c] via-[#0a0a0c] to-transparent pt-20">
          <form onSubmit={handleStartDebate} className="w-full max-w-4xl bg-[#161618] rounded-full p-2 pl-6 flex items-center border border-white/[0.05]">
            <div className="flex items-center justify-center shrink-0 mr-4"><Zap className="w-5 h-5 text-white" /></div>
            <input type="text" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="ENTER DEBATE TOPIC..." className="flex-1 bg-transparent border-none outline-none text-white/80 font-['JetBrains_Mono'] text-xs tracking-widest placeholder:text-white/30 font-semibold" />
            <button type="submit" disabled={!!typingAgent} className="bg-white text-black px-6 py-3.5 rounded-full flex items-center gap-2 hover:bg-white/90 transition-transform active:scale-95 shrink-0 ml-2 disabled:opacity-50 disabled:cursor-not-allowed">
              <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">{typingAgent ? 'Debating...' : 'Start Debate'}</span>
              <span className="text-[#facc15]">{'\u26A1'}</span>
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}