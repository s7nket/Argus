import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  History, 
  Gavel,
  Radio,
  Zap,
  User,
  X,
  Brain,
  ArrowLeft
} from 'lucide-react';
import { cn } from '../lib/utils';
import { useNavigate } from 'react-router';

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
        const res = await fetch('http://localhost:8000/judge/health');
        const data = await res.json();
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

    const ws = new WebSocket('ws://localhost:8000/ws/debate');
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

  const hasStarted = isDebating || messages.length > 0;

  return (
    <div className="flex h-screen w-full bg-[#0a0a0c] text-white font-sans overflow-hidden selection:bg-white/20">
      
      {/* Sidebar */}
      <aside className="w-[280px] shrink-0 bg-[#161618] flex flex-col justify-between hidden md:flex z-20">
        <div>
          <div className="h-20 flex items-center px-8 cursor-pointer" onClick={() => navigate('/')}>
            <span className="font-['Orbitron'] font-bold text-2xl tracking-widest text-white/90">ARGUS</span>
          </div>
          <div className="px-8 py-6 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-black border border-white/10 flex items-center justify-center shrink-0">
              <User className="w-5 h-5 text-white/60" />
            </div>
            <div className="flex flex-col">
              <span className="font-['Orbitron'] text-xs font-bold text-white tracking-widest">OPERATOR-01</span>
              <div className="flex items-center gap-1.5 mt-1">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                <span className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest uppercase">ACTIVE SESSION</span>
              </div>
            </div>
          </div>
          <nav className="px-4 mt-8 flex flex-col gap-1.5">
            {[
              { id: 'active', label: 'ACTIVE DEBATES', icon: Radio, active: true },
              { id: 'history', label: 'DEBATE HISTORY', icon: History },
              { id: 'logs', label: 'JUDGE LOGS', icon: Gavel },
            ].map((item) => (
              <button key={item.id} className={cn("flex items-center gap-4 px-4 py-3 rounded-xl text-left transition-colors duration-200 relative", item.active ? "active bg-white/[0.06] text-white" : "text-white/40 hover:text-white hover:bg-white/[0.02]")}>
                {item.active && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-1/2 bg-white rounded-r-md" />}
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">{item.label}</span>
              </button>
            ))}
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
        <div className="absolute top-0 left-0 w-full p-8 md:p-12 z-10 pointer-events-none">
          <h1 className="sr-only">Debate Dashboard</h1>
          <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-[0.2em] uppercase mb-4 font-bold">SIMULATION PROTOCOL V4.2.0</div>
          <h1 className="font-['Orbitron'] text-4xl md:text-5xl lg:text-6xl font-black tracking-[0.1em] text-transparent" style={{ WebkitTextStroke: '1.5px rgba(255,255,255,0.15)' }}>
            {!hasStarted ? 'INITIALIZING ARENA...' : isDebating ? 'ARENA ACTIVE' : 'DEBATE CONCLUDED'}
          </h1>
        </div>

        {!hasStarted ? (
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
                      <p className="font-['DM_Sans'] text-sm text-white/50 leading-relaxed">{msg.data.reasoning}</p>
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
                const accuracy = d.accuracy ?? { pro: 0, con: 0 };
                const winnerAnalysis = d.winner ?? {};
                const loserAnalysis = d.loser ?? {};
                const fallacies: string[] = d.fallacies ?? [];
                const verdictText: string = d.verdict ?? d.final_reasoning ?? '';
                // support both old field name (strengths) and new (points)
                const winnerPoints: string[] = winnerAnalysis.points ?? winnerAnalysis.strengths ?? [];
                // support both old field name (missed_opportunities) and new (missed_points)
                const loserMissed: string[] = loserAnalysis.missed_points ?? loserAnalysis.missed_opportunities ?? [];
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

                      {/* Header */}
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                          <Gavel className="w-5 h-5" />
                        </div>
                        <div>
                          <span className="font-['Orbitron'] text-lg font-bold text-white block tracking-widest">FINAL VERDICT</span>
                          <span className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest uppercase">JUDGE-0 OMNI · FT SCORER + GROQ VERDICT</span>
                        </div>
                      </div>
                      <div className="h-[1px] bg-white/[0.05] mb-6" />

                      {/* Winner Announcement */}
                      <div className={`${winnerConfig.bg} border ${winnerConfig.border} rounded-2xl p-5 text-center mb-6`}>
                        <span className={`font-['Orbitron'] text-2xl font-black tracking-widest ${winnerConfig.color}`}>
                          {winnerConfig.label}
                        </span>
                        {winnerAnalysis.decisive_argument && (
                          <p className="font-['DM_Sans'] text-sm text-white/70 mt-3 leading-relaxed">
                            "{winnerAnalysis.decisive_argument}"
                          </p>
                        )}
                      </div>

                      {/* Score Breakdown with Accuracy */}
                      <div className="grid grid-cols-2 gap-4 mb-3">
                        {/* PRO */}
                        <div className="bg-emerald-500/[0.04] border border-emerald-500/10 rounded-2xl p-4">
                          <div className="font-['DM_Sans'] text-xs text-emerald-400/70 font-semibold uppercase mb-2">Agent 01 — PRO side</div>
                          <div className="font-['DM_Sans'] text-3xl font-semibold text-white mb-1">
                            {proTotal}<span className="text-sm text-white/30">/30</span>
                          </div>
                          <div className="font-['DM_Sans'] text-xs text-emerald-400/70 mb-3">{accuracy.pro.toFixed(1)}% of possible points</div>
                          <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-400 rounded-full transition-all duration-1000"
                              style={{ width: `${(proTotal / 30) * 100}%` }}
                            />
                          </div>
                        </div>
                        {/* CON */}
                        <div className="bg-rose-500/[0.04] border border-rose-500/10 rounded-2xl p-4">
                          <div className="font-['DM_Sans'] text-xs text-rose-400/70 font-semibold uppercase mb-2">Agent 02 — CON side</div>
                          <div className="font-['DM_Sans'] text-3xl font-semibold text-white mb-1">
                            {conTotal}<span className="text-sm text-white/30">/30</span>
                          </div>
                          <div className="font-['DM_Sans'] text-xs text-rose-400/70 mb-3">{accuracy.con.toFixed(1)}% of possible points</div>
                          <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-rose-400 rounded-full transition-all duration-1000"
                              style={{ width: `${(conTotal / 30) * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>

                      {/* Score Explanations */}
                      {(d.score_explanation?.pro || d.score_explanation?.con) && (
                        <div className="grid grid-cols-2 gap-4 mb-6">
                          {d.score_explanation?.pro && (
                            <div className="bg-white/[0.02] rounded-xl px-3 py-2.5">
                              <div className="font-['DM_Sans'] text-[10px] text-white/30 font-semibold uppercase mb-1">Why PRO got this score</div>
                              <p className="font-['DM_Sans'] text-xs text-white/55 leading-snug">{d.score_explanation.pro}</p>
                            </div>
                          )}
                          {d.score_explanation?.con && (
                            <div className="bg-white/[0.02] rounded-xl px-3 py-2.5">
                              <div className="font-['DM_Sans'] text-[10px] text-white/30 font-semibold uppercase mb-1">Why CON got this score</div>
                              <p className="font-['DM_Sans'] text-xs text-white/55 leading-snug">{d.score_explanation.con}</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Winner / Loser Deep-Dive — specific points */}
                      {(winnerPoints.length > 0 || loserAnalysis.fatal_weakness || loserMissed.length > 0) && (
                        <div className="grid grid-cols-2 gap-4 mb-6">
                          <div className="bg-emerald-500/[0.03] border border-emerald-500/10 rounded-2xl p-4 flex flex-col gap-2">
                            <div className="font-['DM_Sans'] text-xs font-bold text-emerald-400/80 uppercase mb-1">
                              Winning points
                            </div>
                            {winnerPoints.map((s: string, i: number) => (
                              <div key={i} className="flex items-start gap-2">
                                <span className="text-emerald-400 text-sm shrink-0">▲</span>
                                <span className="font-['DM_Sans'] text-sm text-white/75 leading-snug">{s}</span>
                              </div>
                            ))}
                            {winnerAnalysis.strongest_round && (
                              <div className="mt-2 font-['DM_Sans'] text-xs text-white/30">
                                Best round: Round {winnerAnalysis.strongest_round}
                              </div>
                            )}
                          </div>
                          <div className="bg-rose-500/[0.03] border border-rose-500/10 rounded-2xl p-4 flex flex-col gap-2">
                            <div className="font-['DM_Sans'] text-xs font-bold text-rose-400/80 uppercase mb-1">
                              Why they lost
                            </div>
                            {loserAnalysis.fatal_weakness && (
                              <div className="flex items-start gap-2">
                                <span className="text-rose-400 text-sm shrink-0">✗</span>
                                <span className="font-['DM_Sans'] text-sm text-white/75 leading-snug">{loserAnalysis.fatal_weakness}</span>
                              </div>
                            )}
                            {loserMissed.map((m: string, i: number) => (
                              <div key={i} className="flex items-start gap-2">
                                <span className="text-amber-400/80 text-sm shrink-0">–</span>
                                <span className="font-['DM_Sans'] text-sm text-white/60 leading-snug">{m}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Round-by-Round Breakdown */}
                      {rounds.length > 0 && (
                        <div className="mb-6">
                          <div className="font-['DM_Sans'] text-xs font-bold text-white/40 uppercase mb-2">Round by Round</div>
                          <div className="border border-white/[0.05] rounded-xl overflow-hidden">
                            <div className="grid grid-cols-4 bg-white/[0.03] px-4 py-2">
                              {['Round', 'Winner', 'Gap', 'Key Argument'].map(h => (
                                <span key={h} className="font-['DM_Sans'] text-[10px] font-semibold text-white/30 uppercase">{h}</span>
                              ))}
                            </div>
                            {rounds.map((rv: any, i: number) => (
                              <div key={i} className={`grid grid-cols-4 px-4 py-3 items-start ${i % 2 === 0 ? 'bg-white/[0.02]' : ''}`}>
                                <span className="font-['DM_Sans'] text-xs text-white/50">Round {rv.r}</span>
                                <span className={cn(
                                  "font-['DM_Sans'] text-xs font-bold",
                                  rv.winner === 'pro' && 'text-emerald-400',
                                  rv.winner === 'con' && 'text-rose-400',
                                  rv.winner === 'tie' && 'text-yellow-400',
                                )}>
                                  {rv.winner === 'pro' ? 'PRO ▲' : rv.winner === 'con' ? 'CON ▲' : 'TIE'}
                                </span>
                                <span className="font-['DM_Sans'] text-xs text-white/40">
                                  {typeof rv.margin === 'number' ? `+${rv.margin.toFixed(1)}` : `+${rv.margin}`} pts
                                </span>
                                <span className="font-['DM_Sans'] text-xs text-white/55 leading-snug pr-1">{rv.swing}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Flagged Fallacies */}
                      {fallacies.length > 0 && (
                        <div className="border border-amber-500/10 bg-amber-500/[0.03] rounded-xl px-4 py-3 mb-6 flex flex-col gap-1.5">
                          <div className="font-['DM_Sans'] text-xs font-bold text-amber-400/80 uppercase mb-1">⚠ Logical Mistakes Spotted</div>
                          {fallacies.map((f: string, i: number) => (
                            <span key={i} className="font-['DM_Sans'] text-xs text-amber-300/70">{f}</span>
                          ))}
                        </div>
                      )}

                      {/* 3-Sentence Plain Verdict */}
                      {verdictText && (
                        <div className="bg-white/[0.03] border border-white/[0.08] rounded-2xl p-5">
                          <div className="flex items-center gap-2 mb-3">
                            <Gavel className="w-3.5 h-3.5 text-indigo-400" />
                            <span className="font-['DM_Sans'] text-xs font-bold text-indigo-400 uppercase tracking-wide">Judge's Final Call</span>
                          </div>
                          <p className="font-['DM_Sans'] text-sm text-white/80 leading-relaxed">{verdictText}</p>
                        </div>
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