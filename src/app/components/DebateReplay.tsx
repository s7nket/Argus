import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import { ArrowLeft, Gavel, Share2, Check } from 'lucide-react';
import { api } from '../lib/api';
import { cn } from '../lib/utils';

function asText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(' ');
  if (typeof value === 'object')
    return Object.values(value as Record<string, unknown>).map(asText).filter(Boolean).join(' ');
  return String(value);
}

export function DebateReplay() {
  const { debateId } = useParams<{ debateId: string }>();
  const navigate = useNavigate();
  const [debate, setDebate] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!debateId) return;
    (async () => {
      try {
        const res = await fetch(api(`/debates/${debateId}`));
        if (!res.ok) throw new Error('Debate not found');
        setDebate(await res.json());
      } catch (e: any) {
        setError(e.message ?? 'Failed to load debate');
      } finally {
        setLoading(false);
      }
    })();
  }, [debateId]);

  const handleCopy = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0c] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="flex gap-1.5">
            {[0, 150, 300].map((d) => (
              <div key={d} className="w-2 h-2 bg-white/30 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
            ))}
          </div>
          <span className="font-['JetBrains_Mono'] text-[11px] text-white/30 tracking-widest uppercase">Loading debate…</span>
        </div>
      </div>
    );
  }

  if (error || !debate) {
    return (
      <div className="min-h-screen bg-[#0a0a0c] flex items-center justify-center">
        <div className="text-center">
          <p className="font-['JetBrains_Mono'] text-xs text-red-400 tracking-widest mb-4">{error ?? 'Debate not found'}</p>
          <button onClick={() => navigate('/')} className="font-['JetBrains_Mono'] text-[11px] text-white/40 hover:text-white tracking-widest uppercase transition-colors">
            ← Back to Argus
          </button>
        </div>
      </div>
    );
  }

  const final = debate.final_verdict ?? {};
  const winner = final.overall_winner as 'pro' | 'con' | 'tie' | undefined;
  const winnerConfig = winner
    ? {
        pro: { label: 'PRO WINS', color: 'text-emerald-400', border: 'border-emerald-500/30', bg: 'bg-emerald-500/[0.06]' },
        con: { label: 'CON WINS', color: 'text-rose-400', border: 'border-rose-500/30', bg: 'bg-rose-500/[0.06]' },
        tie: { label: 'TIE', color: 'text-yellow-400', border: 'border-yellow-500/30', bg: 'bg-yellow-500/[0.04]' },
      }[winner]
    : null;

  const SUB_COLORS: Record<number, string> = {
    1: 'text-sky-400/70 border-sky-500/20',
    2: 'text-amber-400/70 border-amber-500/20',
    3: 'text-violet-400/70 border-violet-500/20',
  };

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-white font-sans">
      {/* Top nav */}
      <header className="sticky top-0 z-30 bg-[#0a0a0c]/90 backdrop-blur-md border-b border-white/[0.05]">
        <div className="max-w-3xl mx-auto px-6 h-16 flex items-center justify-between">
          <button
            onClick={() => navigate('/debate-dashboard')}
            className="flex items-center gap-2 text-white/40 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-['JetBrains_Mono'] text-[11px] tracking-widest uppercase">Back</span>
          </button>
          <span className="font-['Orbitron'] font-bold text-lg tracking-widest text-white/90 cursor-pointer" onClick={() => navigate('/')}>
            ARGUS
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:border-white/30 bg-white/[0.03] hover:bg-white/[0.06] transition-all"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Share2 className="w-3.5 h-3.5 text-white/50" />}
            <span className="font-['JetBrains_Mono'] text-[10px] tracking-widest uppercase text-white/50">
              {copied ? 'Copied!' : 'Share'}
            </span>
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 pb-24">
        {/* Winner banner */}
        {winnerConfig && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className={cn('rounded-2xl border p-6 mb-8 text-center', winnerConfig.border, winnerConfig.bg)}
          >
            <p className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-2">Final Result</p>
            <p className={cn('font-["Orbitron"] text-3xl font-bold tracking-widest', winnerConfig.color)}>
              {winnerConfig.label}
            </p>
            {final.pro_total != null && (
              <p className="font-['JetBrains_Mono'] text-[11px] text-white/40 tracking-widest mt-2">
                PRO {final.pro_total} · CON {final.con_total}
              </p>
            )}
          </motion.div>
        )}

        {/* Topic */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
          <h1 className="font-['DM_Sans'] text-2xl font-semibold text-white/90 mb-2">{asText(debate.topic)}</h1>
          <p className="font-['JetBrains_Mono'] text-[10px] text-white/30 tracking-widest uppercase mb-10">
            {new Date(debate.created_at).toLocaleString()} · {(debate.rounds ?? []).length} rounds
          </p>
        </motion.div>

        {/* Rounds */}
        {(debate.rounds ?? []).map((r: any, ri: number) => (
          <motion.div
            key={r.round}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + ri * 0.05 }}
            className="mb-10"
          >
            {/* Sub-round speeches */}
            {Array.from(new Set((r.exchange ?? []).map((s: any) => s.sub_round))).map((sr: any) => (
              <div key={sr} className="mb-6">
                {/* Sub-round divider */}
                <div className="flex items-center gap-4 mb-4">
                  <div className="h-[1px] bg-white/[0.04] flex-1" />
                  <div className={cn('border px-4 py-1.5 rounded-full', SUB_COLORS[sr] ?? 'text-white/40 border-white/10')}>
                    <span className="font-['JetBrains_Mono'] text-[9px] tracking-[0.2em] uppercase font-bold">
                      R{r.round} · {sr === 1 ? 'OPENING' : sr === 2 ? 'REBUTTAL' : 'JUSTIFY'}
                    </span>
                  </div>
                  <div className="h-[1px] bg-white/[0.04] flex-1" />
                </div>

                {/* Speeches for this sub-round */}
                {(r.exchange ?? [])
                  .filter((s: any) => s.sub_round === sr)
                  .map((speech: any, si: number) => (
                    <div
                      key={si}
                      className={cn(
                        'flex flex-col gap-2 mb-5',
                        speech.speaker === 'con' ? 'items-end text-right' : 'items-start'
                      )}
                    >
                      <div className={cn('flex items-center gap-3', speech.speaker === 'con' ? 'flex-row-reverse' : '')}>
                        <div className={cn(
                          'px-3 py-1 rounded-full border text-[10px] font-bold tracking-widest font-["JetBrains_Mono"] shrink-0',
                          speech.speaker === 'pro'
                            ? 'bg-white/10 border-white/10 text-white'
                            : 'bg-white text-black border-transparent'
                        )}>
                          {speech.speaker === 'pro' ? 'AGENT-01' : 'AGENT-02'}
                        </div>
                        <span className={cn(
                          "font-['JetBrains_Mono'] text-[10px] tracking-widest font-bold",
                          speech.speaker === 'pro' ? 'text-emerald-400/80' : 'text-rose-400/80'
                        )}>
                          {speech.speaker.toUpperCase()}
                        </span>
                      </div>
                      <p className="font-['DM_Sans'] text-[15px] text-white/75 leading-[1.65] font-light max-w-xl">
                        {asText(speech.text)}
                      </p>
                    </div>
                  ))}
              </div>
            ))}

            {/* Round verdict */}
            {r.round_winner && (
              <div className="bg-indigo-500/[0.06] border border-indigo-500/20 rounded-2xl p-5 mt-4">
                <div className="font-['JetBrains_Mono'] text-[10px] text-indigo-400 tracking-widest uppercase mb-3 font-bold flex items-center gap-2">
                  <Gavel className="w-3.5 h-3.5" /> ROUND {r.round} VERDICT
                </div>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  {[
                    { label: 'PRO', total: r.pro_scores?.total, color: 'text-emerald-400' },
                    { label: 'CON', total: r.con_scores?.total, color: 'text-rose-400' },
                  ].map(({ label, total, color }) => (
                    <div key={label} className="bg-white/[0.03] rounded-xl p-3 text-center">
                      <div className="font-['JetBrains_Mono'] text-[9px] text-white/40 tracking-widest mb-1">{label}</div>
                      <div className={cn('text-xl font-["DM_Sans"] font-semibold', color)}>
                        {total ?? '—'}<span className="text-xs text-white/30">/10</span>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="font-['JetBrains_Mono'] text-[10px] text-white/50 tracking-widest uppercase mb-2">
                  Winner: <span className="text-white font-bold">{String(r.round_winner).toUpperCase()}</span>
                </p>
                {r.reasoning && (
                  <p className="font-['DM_Sans'] text-sm text-white/45 leading-relaxed">{asText(r.reasoning)}</p>
                )}
              </div>
            )}
          </motion.div>
        ))}

        {/* Final verdict */}
        {final.verdict && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-[#111114] border border-white/10 rounded-3xl p-8 mb-10"
          >
            <div className="font-['JetBrains_Mono'] text-[10px] text-white/40 tracking-widest uppercase mb-4 flex items-center gap-2">
              <Gavel className="w-3.5 h-3.5" /> Final Verdict
            </div>
            <p className="font-['DM_Sans'] text-[15px] text-white/80 leading-relaxed">{asText(final.verdict)}</p>
          </motion.div>
        )}

        {/* Watermark / CTA */}
        <div className="text-center pt-8 border-t border-white/[0.05]">
          <p className="font-['JetBrains_Mono'] text-[10px] text-white/25 tracking-widest uppercase mb-3">
            Debated on Argus · AI-powered argument analysis
          </p>
          <button
            onClick={() => navigate('/debate-dashboard')}
            className="font-['JetBrains_Mono'] text-[11px] text-white/40 hover:text-white tracking-widest uppercase transition-colors border border-white/10 hover:border-white/30 px-5 py-2.5 rounded-full"
          >
            Start your own debate →
          </button>
        </div>
      </main>
    </div>
  );
}
