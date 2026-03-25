import React from 'react';
import { motion, useInView } from 'motion/react';
import { GlassCard } from './GlassCard';
import { Check } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';

import { useNavigate } from 'react-router';

import imgLayout1 from '../../assets/layout1.png';

export function DebateInAction() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const navigate = useNavigate();

  const features = [
    'Real-time argument generation',
    'Fallacy detection engine',
    'Multi-round debate flow',
    'Live scoring per argument'
  ];

  return (
    <section ref={ref} className="container mx-auto px-6 md:px-20 max-w-[1440px] py-16 md:py-24 overflow-hidden">
      
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7 }}
        className="will-change-[transform,opacity] transform-gpu"
        onAnimationComplete={() => {
          // Release will-change if possible, but framer motion handles it mostly
        }}
      >
        <GlassCard className="w-full flex flex-col md:flex-row items-stretch border border-white/10 shadow-2xl p-0 overflow-hidden">
          
          {/* Left Image */}
          <div className="w-full md:w-1/2 relative bg-white/5 flex items-center justify-center overflow-hidden">
            <ImageWithFallback 
              src={imgLayout1} 
              alt="Robot Profiling" 
              className="w-full h-full min-h-[400px] object-cover object-center scale-105 hover:scale-110 transition-transform duration-700 ease-out will-change-transform transform-gpu"
              loading="lazy"
              decoding="async"
            />
          </div>

          {/* Right Content */}
          <div className="w-full md:w-1/2 p-8 md:p-12 lg:p-16 flex flex-col justify-center">
            <span className="font-['JetBrains_Mono'] text-[10px] text-white/50 uppercase tracking-[0.2em] mb-4">
              For Researchers & Builders
            </span>
            
            <h2 className="font-['Orbitron'] text-2xl md:text-3xl font-bold text-white mb-5 leading-tight tracking-wide">
              Run any argument.<br className="hidden md:block"/> At scale.
            </h2>
            
            <p className="font-['DM_Sans'] text-sm md:text-base text-white/70 leading-relaxed mb-8 max-w-lg">
              ARGUS processes any debate topic, assigns agents to opposing sides, generates structured arguments round by round, scores each move, and reveals the winner with full reasoning — all inside the platform.
            </p>

            <div className="flex flex-col gap-3 w-full max-w-md">
              {features.map((feature, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl hover:border-white/20 transition-colors duration-200">
                  <Check className="w-4 h-4 text-white shrink-0" />
                  <span className="font-['JetBrains_Mono'] text-xs font-semibold text-white/90">
                    {feature}
                  </span>
                </div>
              ))}
            </div>

            <button onClick={() => navigate('/dashboard')} className="mt-8 bg-white text-black font-['DM_Sans'] text-sm md:text-base font-bold py-3 px-7 rounded-full hover:bg-black hover:text-white border-2 border-transparent hover:border-white transition-colors duration-300 shadow-[0_0_20px_rgba(255,255,255,0.2)] w-fit will-change-transform transform-gpu">
              Watch a Live Debate &rarr;
            </button>
          </div>
        </GlassCard>
      </motion.div>

    </section>
  );
}