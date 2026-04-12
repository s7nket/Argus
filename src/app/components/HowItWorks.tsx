import React from 'react';
import { motion, useInView } from 'motion/react';
import { GlassCard } from './GlassCard';
import { Diamond, XCircle, SquareDot } from 'lucide-react';
import { useNavigate } from 'react-router';

export function HowItWorks() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const navigate = useNavigate();

  const cards = [
    {
      icon: <Diamond className="w-5 h-5 text-white/80" />,
      title: 'Agent A · Proponent',
      body: 'Agent A presents arguments — constructs structured claims, pulls evidence, and adapts in real-time.'
    },
    {
      icon: <XCircle className="w-5 h-5 text-white/80" />,
      title: 'Agent B · Opponent',
      body: 'Deconstructs claims, exposes logical gaps, counter-argues with precision.'
    },
    {
      icon: <SquareDot className="w-5 h-5 text-white/80" />,
      title: 'Judge-0 · Evaluator',
      body: 'Scores each round. Detects fallacies. Delivers an unbiased final verdict.'
    }
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
          System Architecture
        </span>
        <h2 className="font-['Orbitron'] text-3xl md:text-4xl font-bold text-white mb-1 tracking-wide">
          How It Works
        </h2>
        <p className="font-['DM_Sans'] text-white/50 text-sm mb-2">
          Intelligence that argues.
        </p>
        <p className="font-['DM_Sans'] text-white/60 italic text-base md:text-lg">
          Two agents. One judge. Zero bias.
        </p>
      </motion.div>

      <div className="flex overflow-x-auto md:grid md:grid-cols-3 gap-6 w-full snap-x snap-mandatory pb-8 md:pb-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden mb-16">
        {cards.map((card, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 40 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.2 + i * 0.1 }}
            className="will-change-[transform,opacity] transform-gpu"
          >
            <GlassCard className="min-w-[85vw] md:min-w-0 p-10 flex flex-col gap-6 snap-center items-start justify-start h-full">
              <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center border border-white/10">
                {card.icon}
              </div>
              <h3 className="font-['JetBrains_Mono'] text-xs font-bold text-white tracking-widest uppercase">
                {card.title}
              </h3>
              <p className="font-['DM_Sans'] text-sm md:text-base text-white/70 leading-relaxed">
                {card.body}
              </p>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <div className="flex justify-center w-full">
        <button onClick={() => navigate('/debate-dashboard')} className="flex items-center gap-2 px-6 py-3 rounded-full border border-white/20 bg-transparent text-white/80 hover:text-white hover:bg-white/5 transition-colors duration-200 font-['JetBrains_Mono'] text-xs tracking-widest uppercase will-change-transform transform-gpu">
          Ready to see it live? <span className="text-white ml-2">→ Go to Debate</span>
        </button>
      </div>
    </section>
  );
}