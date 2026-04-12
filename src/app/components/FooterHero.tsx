import React from 'react';
import { motion, useInView } from 'motion/react';
import { ArrowRight, Triangle } from 'lucide-react';
import { useNavigate } from 'react-router';

export function FooterHero() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const navigate = useNavigate();

  return (
    <footer ref={ref} className="w-full pt-20 pb-10 flex flex-col items-center justify-center relative overflow-hidden">
      
      {/* Decorative Line effect */}
      <div className="absolute top-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent" />

      {/* Main CTA */}
      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7 }}
        className="flex flex-col items-center text-center px-6 mb-24 z-10 will-change-[transform,opacity] transform-gpu"
      >
        <h2 className="font-['Orbitron'] text-5xl md:text-7xl leading-tight font-bold text-white mb-4 tracking-wide">
          Start Debate
        </h2>
        <p className="font-['DM_Sans'] text-lg md:text-xl text-white/50 mb-10 italic">
          Free your reasoning.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-4">
          <button onClick={() => navigate('/debate-dashboard')} className="w-full sm:w-auto px-8 py-4 rounded-full bg-white text-black font-['DM_Sans'] text-base font-bold hover:bg-black hover:text-white border-2 border-transparent hover:border-white transition-colors duration-300 shadow-[0_0_20px_rgba(255,255,255,0.2)] will-change-transform transform-gpu">
            Start Debate
          </button>
          <button className="w-full sm:w-auto px-8 py-4 rounded-full bg-transparent text-white font-['DM_Sans'] text-base font-semibold border border-white hover:bg-white/10 transition-colors duration-300 flex items-center justify-center gap-2 will-change-transform transform-gpu">
            View Sample Debate <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </motion.div>

      {/* Footer Grid */}
      <div className="container mx-auto px-6 md:px-20 max-w-[1440px] flex flex-col md:flex-row justify-between items-start md:items-center gap-10 border-t border-white/[0.05] pt-10">
        
        <div className="flex items-center gap-3">
          <Triangle className="w-4 h-4 fill-white text-white rotate-180" />
          <span className="font-['Orbitron'] font-bold text-lg tracking-wider uppercase text-white/80">Argus</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-12 text-left">
          <div className="flex flex-col gap-3">
            <span className="font-['JetBrains_Mono'] text-[11px] text-white/60 uppercase tracking-widest mb-2">Plan</span>
            {['Free Tier', 'Pro Model', 'Enterprise', 'API Pricing'].map(link => (
              <a key={link} href="#" className="font-['DM_Sans'] text-[12px] text-white/40 hover:text-white/80 transition-colors">
                {link}
              </a>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            <span className="font-['JetBrains_Mono'] text-[11px] text-white/60 uppercase tracking-widest mb-2">Company</span>
            {['About Us', 'Careers', 'Research', 'Contact'].map(link => (
              <a key={link} href="#" className="font-['DM_Sans'] text-[12px] text-white/40 hover:text-white/80 transition-colors">
                {link}
              </a>
            ))}
          </div>
          <div className="flex flex-col gap-3 col-span-2 md:col-span-1">
            <span className="font-['JetBrains_Mono'] text-[11px] text-white/60 uppercase tracking-widest mb-2">Links</span>
            {['Documentation', 'GitHub', 'Discord', 'X / Twitter'].map(link => (
              <a key={link} href="#" className="font-['DM_Sans'] text-[12px] text-white/40 hover:text-white/80 transition-colors">
                {link}
              </a>
            ))}
          </div>
        </div>

      </div>
    </footer>
  );
}