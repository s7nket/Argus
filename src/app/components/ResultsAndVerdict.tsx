import React from 'react';
import { motion, useInView } from 'motion/react';
import { GlassCard } from './GlassCard';
import { useNavigate } from 'react-router';

export function ResultsAndVerdict() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const navigate = useNavigate();

  const rows = [
    { round: 1, agent: 'Agent A', summary: 'Cited empirical data', score: '8.4', loser: false },
    { round: 1, agent: 'Agent B', summary: 'Logical counter, weak', score: '6.1', loser: true },
    { round: 2, agent: 'Agent A', summary: 'Strong rebuttal', score: '9.2', loser: false },
    { round: 2, agent: 'Agent B', summary: 'Fallacy detected ⚠️', score: '4.0', loser: true },
  ];

  return (
    <section ref={ref} className="container mx-auto px-6 md:px-20 max-w-[1440px] flex flex-col items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center text-center mb-16 will-change-[transform,opacity] transform-gpu"
      >
        <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 uppercase tracking-[0.2em] mb-4">
          Results & Scoring
        </span>
        <h2 className="font-['Orbitron'] text-3xl md:text-4xl font-bold text-white mb-6 tracking-wide max-w-2xl leading-tight">
          Who won. Why they won. How every argument was scored — in real time.
        </h2>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="will-change-[transform,opacity] transform-gpu"
      >
        <GlassCard className="w-full max-w-4xl p-8 md:p-12 flex flex-col gap-8 mx-auto">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[600px]">
              <thead>
                <tr className="border-b border-white/[0.15]">
                  <th className="py-4 px-4 font-['JetBrains_Mono'] text-xs uppercase tracking-widest text-white/70 font-medium">Round</th>
                  <th className="py-4 px-4 font-['JetBrains_Mono'] text-xs uppercase tracking-widest text-white/70 font-medium">Agent</th>
                  <th className="py-4 px-4 font-['JetBrains_Mono'] text-xs uppercase tracking-widest text-white/70 font-medium">Argument Summary</th>
                  <th className="py-4 px-4 font-['JetBrains_Mono'] text-xs uppercase tracking-widest text-white/70 font-medium text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={idx} className={`border-b border-white/[0.05] font-['DM_Sans'] text-sm md:text-base ${row.loser ? 'opacity-50' : 'text-white'}`}>
                    <td className="py-4 px-4 font-['JetBrains_Mono']">{row.round}</td>
                    <td className="py-4 px-4 font-bold">{row.agent}</td>
                    <td className="py-4 px-4">{row.summary}</td>
                    <td className="py-4 px-4 font-['JetBrains_Mono'] text-right font-bold">{row.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <GlassCard className="p-6 flex flex-col gap-2 mt-4">
            <h3 className="font-['Orbitron'] text-xl md:text-2xl font-bold text-white uppercase tracking-wider">
              WINNER: AGENT A
            </h3>
            <p className="font-['DM_Sans'] text-sm md:text-base text-white/90 leading-relaxed italic">
              Winning argument: "Round 2 rebuttal — empirical evidence + structural logic with zero fallacies."
            </p>
          </GlassCard>
        </GlassCard>
      </motion.div>

      <div className="flex justify-center w-full mt-12">
        <button onClick={() => navigate('/debate-dashboard')} className="flex items-center gap-2 px-8 py-4 rounded-full border border-white/20 bg-transparent text-white/80 hover:text-white hover:bg-white/5 transition-colors duration-200 font-['JetBrains_Mono'] text-xs md:text-sm tracking-widest uppercase will-change-transform transform-gpu">
          See a Real Verdict <span className="text-white ml-2">→</span>
        </button>
      </div>
    </section>
  );
}