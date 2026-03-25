import React, { useState } from 'react';
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

// The image mentioned by user
const dashboardImage = '';

export function DebateDashboard() {
  const navigate = useNavigate();
  const [judgeOpen, setJudgeOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [isDebating, setIsDebating] = useState(false);

  const handleStartDebate = React.useCallback((e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!prompt.trim()) return;
    setIsDebating(true);
  }, [prompt]);

  return (
    <div className="flex h-screen w-full bg-[#0a0a0c] text-white font-sans overflow-hidden selection:bg-white/20">
      
      {/* Sidebar */}
      <aside className="w-[280px] shrink-0 bg-[#161618] flex flex-col justify-between hidden md:flex z-20">
        <div>
          {/* Logo */}
          <div className="h-20 flex items-center px-8 cursor-pointer" onClick={() => navigate('/')}>
            <span className="font-['Orbitron'] font-bold text-2xl tracking-widest text-white/90">ARGUS</span>
          </div>

          {/* User Profile */}
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

          {/* Nav Links */}
          <nav className="px-4 mt-8 flex flex-col gap-1.5">
            {[
              { id: 'active', label: 'ACTIVE DEBATES', icon: Radio, active: true },
              { id: 'history', label: 'DEBATE HISTORY', icon: History },
              { id: 'logs', label: 'JUDGE LOGS', icon: Gavel },
            ].map((item) => (
              <button
                key={item.id}
                className={cn(
                  "flex items-center gap-4 px-4 py-3 rounded-xl text-left transition-colors duration-200 relative",
                  item.active ? "bg-white/[0.06] text-white" : "text-white/40 hover:text-white hover:bg-white/[0.02]"
                )}
              >
                {item.active && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-1/2 bg-white rounded-r-md" />
                )}
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">
                  {item.label}
                </span>
              </button>
            ))}
          </nav>
        </div>
        
        {/* Bottom Back Button */}
        <div className="p-6">
          <button 
            onClick={() => navigate('/')}
            className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors duration-200"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">
              Main Landing
            </span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 relative h-full">
        
        {/* Top Header / Status */}
        <div className="absolute top-0 left-0 w-full p-8 md:p-12 z-10 pointer-events-none">
          <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-[0.2em] uppercase mb-4 font-bold">
            SIMULATION PROTOCOL V4.2.0
          </div>
          <h1 className="font-['Orbitron'] text-4xl md:text-5xl lg:text-6xl font-black tracking-[0.1em] text-transparent" style={{ WebkitTextStroke: '1.5px rgba(255,255,255,0.15)' }}>
            {!isDebating ? 'INITIALIZING ARENA...' : 'ARENA ACTIVE'}
          </h1>
        </div>

        {!isDebating ? (
          /* Awaiting Parameters State */
          <div className="flex-1 flex flex-col items-center justify-center p-6 mt-10">
            <div className="flex flex-col items-center max-w-[400px] text-center">
              <div className="w-32 h-32 rounded-full border border-dashed border-white/10 flex items-center justify-center mb-10 relative">
                <div className="absolute inset-0 rounded-full bg-white/[0.01]" />
                <div className="w-12 h-12 bg-white/5 rounded-full flex items-center justify-center">
                  <Brain className="w-5 h-5 text-white/30" />
                </div>
              </div>
              <h2 className="font-['Orbitron'] text-xl tracking-[0.2em] text-white/60 mb-4 uppercase font-semibold">
                Awaiting Parameters
              </h2>
              <p className="font-['DM_Sans'] text-sm text-white/30 leading-relaxed font-medium">
                Enter a debate topic below to engage neural simulation protocols and deploy active agents.
              </p>
            </div>
          </div>
        ) : (
          /* Chat Thread */
          <div className="flex-1 overflow-y-auto px-6 md:px-20 lg:px-40 pt-48 pb-48 flex flex-col gap-16 scroll-smooth z-0">
            
            {/* Message 1 (Left) */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col gap-6 max-w-3xl will-change-[transform,opacity] transform-gpu"
            >
              <div className="flex items-center gap-4 w-full">
                <div className="bg-white/10 px-3 py-1 rounded-full border border-white/10 shrink-0">
                  <span className="font-['JetBrains_Mono'] text-[10px] text-white tracking-widest font-bold">AGENT-01</span>
                </div>
                <div className="h-[1px] bg-white/[0.05] flex-1" />
              </div>
              
              <h2 className="font-['DM_Sans'] text-2xl md:text-3xl font-medium text-white leading-tight tracking-tight">
                The decentralization of intelligence is not a choice, but a thermodynamic inevitability.
              </h2>
              
              <p className="font-['DM_Sans'] text-base md:text-lg text-white/70 leading-relaxed font-light">
                Centralized systems suffer from catastrophic information bottlenecks. By distributing inference across the Argus Protocol, we achieve a resilience that mimics biological neural architectures. The efficiency gain is not linear; it is exponential.
              </p>
              
              <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center gap-6 mt-2">
                <span>HASH: 0x82f..21a</span>
                <span>LATENCY: 14ms</span>
              </div>
            </motion.div>

            {/* Message 2 (Right) */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="flex flex-col gap-6 max-w-3xl self-end text-right will-change-[transform,opacity] transform-gpu"
            >
              <div className="flex items-center gap-4 w-full justify-end">
                <div className="h-[1px] bg-white/[0.05] flex-1" />
                <div className="bg-white text-black px-3 py-1 rounded-full shrink-0">
                  <span className="font-['JetBrains_Mono'] text-[10px] tracking-widest font-bold">AGENT-02</span>
                </div>
              </div>
              
              <h2 className="font-['DM_Sans'] text-2xl md:text-3xl font-medium text-white leading-tight tracking-tight">
                Absolute distribution without a steering core leads to entropic divergence.
              </h2>
              
              <p className="font-['DM_Sans'] text-base md:text-lg text-white/70 leading-relaxed font-light">
                Resilience is useless if the system loses semantic coherence. Agent-01 overlooks the coordination cost. Without the Argus Core to align objective functions, the network dissolves into noise—efficient noise, perhaps, but noise nonetheless.
              </p>
              
              <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 uppercase tracking-widest flex items-center justify-end gap-6 mt-2">
                <span>HASH: 0x41b..99d</span>
                <span>LATENCY: 18ms</span>
              </div>
            </motion.div>

            {/* Trigger for Judge Popup */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1 }}
              className="flex justify-center mt-4 will-change-[transform,opacity] transform-gpu"
            >
              <button 
                onClick={() => setJudgeOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors"
              >
                <Gavel className="w-4 h-4" />
                <span className="font-['JetBrains_Mono'] text-xs font-bold tracking-widest uppercase">Request ML Verdict</span>
              </button>
            </motion.div>

          </div>
        )}

        {/* Input Bar */}
        <div className="absolute bottom-0 left-0 right-0 p-6 md:p-12 flex justify-center z-10 bg-gradient-to-t from-[#0a0a0c] via-[#0a0a0c] to-transparent pt-20">
          <form 
            onSubmit={handleStartDebate}
            className="w-full max-w-4xl bg-[#161618] rounded-full p-2 pl-6 flex items-center border border-white/[0.05]"
          >
            <div className="flex items-center justify-center shrink-0 mr-4">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="ENTER DEBATE TOPIC..."
              className="flex-1 bg-transparent border-none outline-none text-white/80 font-['JetBrains_Mono'] text-xs tracking-widest placeholder:text-white/30 font-semibold"
            />
            <button 
              type="submit"
              className="bg-white text-black px-6 py-3.5 rounded-full flex items-center gap-2 hover:bg-white/90 transition-transform active:scale-95 shrink-0 ml-2"
            >
              <span className="font-['JetBrains_Mono'] text-[11px] font-bold tracking-widest uppercase">Start Debate</span>
              <span className="text-[#facc15]">⚡</span>
            </button>
          </form>
        </div>
      </main>

      {/* Judge ML Popup Modal */}
      <AnimatePresence>
        {judgeOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 md:p-6 isolate before:absolute before:inset-0 before:-z-10 before:backdrop-blur-sm will-change-opacity transform-gpu"
              onClick={() => setJudgeOpen(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                onClick={(e) => e.stopPropagation()}
                className="w-full max-w-2xl bg-[#111114] border border-white/10 rounded-3xl overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col relative will-change-[transform,opacity] transform-gpu contain-layout contain-paint"
              >
                {/* Glow effects */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[300px] h-[300px] bg-indigo-500/20 rounded-full blur-[100px] pointer-events-none" />

                <div className="p-6 md:p-8 flex justify-between items-center border-b border-white/5 relative z-10">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                      <Gavel className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="font-['Orbitron'] font-bold text-xl text-white">JUDGE-0 OMNI</h3>
                      <p className="font-['JetBrains_Mono'] text-[10px] text-white/50 tracking-widest uppercase">ML Inference Complete</p>
                    </div>
                  </div>
                  <button onClick={() => setJudgeOpen(false)} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                    <X className="w-5 h-5 text-white/50" />
                  </button>
                </div>

                <div className="p-6 md:p-8 flex flex-col gap-8 relative z-10">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/[0.02] border border-white/[0.05] p-5 rounded-2xl">
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-2 block">Logic Score (A1)</span>
                      <div className="text-3xl font-['DM_Sans'] text-white">84<span className="text-lg text-white/30">/100</span></div>
                    </div>
                    <div className="bg-white/[0.02] border border-white/[0.05] p-5 rounded-2xl">
                      <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-2 block">Logic Score (A2)</span>
                      <div className="text-3xl font-['DM_Sans'] text-white">91<span className="text-lg text-white/30">/100</span></div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h4 className="font-['JetBrains_Mono'] text-[11px] text-indigo-400 tracking-widest uppercase font-bold">Verdict Summary</h4>
                    <p className="font-['DM_Sans'] text-base text-white/80 leading-relaxed">
                      Agent-02 successfully counter-argued Agent-01 by introducing the necessary condition of "semantic coherence." While Agent-01 established the thermodynamic necessity of decentralization, it failed to account for the entropic drift inherent in unsteered systems. Agent-02's framework incorporates coordination cost, proving strictly more robust.
                    </p>
                  </div>

                  <div className="pt-6 border-t border-white/5 flex justify-between items-center">
                    <div className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500 will-change-opacity transform-gpu animate-pulse isolate" />
                      JUDGEMENT RECORDED
                    </div>
                    <button onClick={() => setJudgeOpen(false)} className="bg-white text-black px-6 py-2.5 rounded-full font-['JetBrains_Mono'] text-xs font-bold tracking-widest uppercase hover:bg-white/90 transition-colors">
                      Accept Verdict
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}