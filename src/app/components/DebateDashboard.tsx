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
  const rounds = 3;
  const wsRef = useRef<WebSocket | null>(null);
  const typingStartRef = useRef<number>(0);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typingAgent]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  const handleStartDebate = React.useCallback((e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!prompt.trim() || typingAgent) return;
    setIsDebating(true);
    setMessages([]);
    setTypingAgent(null);
    setDebateComplete(false);
    setError(null);

    const ws = new WebSocket('ws://localhost:8000/ws/debate');
    wsRef.current = ws;
    ws.onopen = () => { ws.send(JSON.stringify({ topic: prompt, rounds })); };

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
          setMessages(prev => [...prev, { type: 'pro', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: 'llama-3.3-70b-versatile' }]);
          break;
        }
        case 'con_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'con', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: 'llama-3.1-8b-instant' }]);
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
          setDebateComplete(true);
          setTypingAgent(null);
          break;
        case 'error':
          setError(msg.message);
          setTypingAgent(null);
          break;
      }
    };
    ws.onerror = () => { setError('WebSocket connection failed. Is the backend running?'); setTypingAgent(null); };
    ws.onclose = () => { wsRef.current = null; };
  }, [prompt, rounds, typingAgent]);

  const lastFinalVerdict = messages.find((m: any) => m.type === 'final_verdict');

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
        <div className="p-6">
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
            {!isDebating ? 'INITIALIZING ARENA...' : 'ARENA ACTIVE'}
          </h1>
        </div>

        {!isDebating ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 mt-10">
            <div className="flex flex-col items-center max-w-[400px] text-center">
              <div className="w-32 h-32 rounded-full border border-dashed border-white/10 flex items-center justify-center mb-10 relative">
                <div className="absolute inset-0 rounded-full bg-white/[0.01]" />
                <div className="w-12 h-12 bg-white/5 rounded-full flex items-center justify-center"><Brain className="w-5 h-5 text-white/30" /></div>
              </div>
              <h2 className="font-['Orbitron'] text-xl tracking-[0.2em] text-white/60 mb-4 uppercase font-semibold">Awaiting Parameters</h2>
              <p className="font-['DM_Sans'] text-sm text-white/30 leading-relaxed font-medium">Enter a debate topic below to engage neural simulation protocols and deploy active agents.</p>
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
                  <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="flex flex-col gap-4 max-w-3xl self-end text-right will-change-[transform,opacity] transform-gpu">
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
                return (
                  <motion.div key={idx} initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: 0.6 }} className="flex justify-center will-change-[transform,opacity] transform-gpu">
                    <div className="bg-[#111114] border border-white/10 rounded-3xl p-8 max-w-2xl w-full shadow-[0_0_60px_rgba(99,102,241,0.08)]">
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400"><Gavel className="w-5 h-5" /></div>
                        <div>
                          <span className="font-['Orbitron'] text-lg font-bold text-white block">FINAL VERDICT</span>
                          <span className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest uppercase">JUDGE-0 OMNI</span>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mb-6">
                        <div className="bg-white/[0.02] border border-white/[0.05] p-5 rounded-2xl text-center">
                          <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-2 block">PRO Total</span>
                          <div className="text-3xl font-['DM_Sans'] text-white font-semibold">{msg.data.pro_total}</div>
                        </div>
                        <div className="bg-white/[0.02] border border-white/[0.05] p-5 rounded-2xl text-center">
                          <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-2 block">CON Total</span>
                          <div className="text-3xl font-['DM_Sans'] text-white font-semibold">{msg.data.con_total}</div>
                        </div>
                      </div>
                      <div className="text-center mb-4">
                        <span className="font-['Orbitron'] text-sm text-white/50 tracking-widest uppercase">OVERALL WINNER: </span>
                        <span className="font-['Orbitron'] text-lg text-white font-bold tracking-widest">{msg.data.overall_winner.toUpperCase()}</span>
                      </div>
                      <p className="font-['DM_Sans'] text-base text-white/70 leading-relaxed text-center">{msg.data.final_reasoning}</p>
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