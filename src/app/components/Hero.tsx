import React from 'react';
import { motion, useScroll, useTransform } from 'motion/react';
import { GlassCard } from './GlassCard';
import { Triangle } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';
import { useNavigate } from 'react-router';
import imgSingleThumb from '../../assets/hero.png';
import imgHero from '../../assets/hero.png';

export function Hero() {
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, 150]);
  const opacity = useTransform(scrollY, [0, 300], [1, 0]);
  const navigate = useNavigate();

  return (
    <section className="relative z-0 min-h-[100svh] pt-24 pb-32 overflow-hidden flex items-center justify-center w-full">
      
      {/* Background Robots Image */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.2 }}
        style={{ y, opacity }}
        className="absolute inset-0 -z-50 w-full h-full transform-gpu will-change-[transform,opacity]"
        onAnimationComplete={() => {
          // Keep transform/opacity for scroll parallax if needed, but framer handles it
        }}
      >
        <ImageWithFallback 
          src={imgHero} 
          alt="Hero Robots Facing" 
          className="w-full h-full object-cover object-bottom" 
          loading="lazy"
          decoding="async"
        />
      </motion.div>

      {/* Pulsing radial glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] -z-30 pointer-events-none transform-gpu isolate will-change-opacity">
        <motion.div
          animate={{ opacity: [0.1, 0.15, 0.1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          className="w-full h-full bg-white rounded-full blur-[160px] mix-blend-screen will-change-opacity transform-gpu"
        />
      </div>

      {/* Dashed Circular Arc */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full border border-dashed border-white/10 -z-20 pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1100px] h-[1100px] rounded-full border border-dashed border-white/5 -z-20 pointer-events-none" />

      {/* Container for content */}
      <div className="relative z-10 container mx-auto px-6 md:px-20 max-w-[1440px] flex flex-col items-center justify-center w-full h-full min-h-[60vh]">
        {/* Center Text */}
        <div className="flex flex-col items-center text-center w-full z-30 relative">
          <motion.h1 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="font-['Orbitron'] font-bold text-7xl md:text-[140px] leading-none tracking-[0.05em] text-white uppercase drop-shadow-[0_0_20px_rgba(255,255,255,0.2)]"
          >
            ARGUS
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="font-['JetBrains_Mono'] text-[11px] md:text-xs uppercase tracking-[0.2em] mt-6 bg-white/10 px-5 py-2 rounded-full border border-white/20 mb-10 relative isolate before:absolute before:inset-0 before:-z-10 before:rounded-full before:backdrop-blur-md will-change-[transform,opacity] transform-gpu"
          >
            Multi-Agent Debate System
          </motion.p>
          
          <motion.button
            onClick={() => navigate('/dashboard')}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.6 }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="bg-white text-black font-['DM_Sans'] text-base md:text-lg font-bold py-3 px-10 rounded-full hover:bg-black hover:text-white border-2 border-transparent hover:border-white transition-colors duration-300 shadow-[0_0_30px_rgba(255,255,255,0.3)] hover:shadow-[0_0_40px_rgba(255,255,255,0.5)] will-change-[transform,opacity] transform-gpu"
          >
            Start Debate
          </motion.button>
        </div>

        {/* Left Bottom Card - Moved down more */}
        <motion.div 
          initial={{ opacity: 0, x: -30, y: 30 }}
          whileInView={{ opacity: 1, x: 0, y: 0 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.6, delay: 0.6 }}
          whileHover={{ y: -8, scale: 1.02 }}
          className="absolute bottom-[-40px] left-6 md:bottom-[-20px] md:left-10 lg:left-20 max-w-sm hidden lg:block z-40 cursor-default will-change-[transform,opacity] transform-gpu"
        >
          <GlassCard className="p-5 border border-white/10 bg-black/40 before:backdrop-blur-xl">
            <h3 className="font-['JetBrains_Mono'] text-[10px] font-bold text-white uppercase tracking-widest mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-white animate-pulse will-change-opacity transform-gpu isolate" />
              Debate-1 × Debate-2
            </h3>
            <p className="font-['DM_Sans'] text-sm text-white/70 leading-relaxed mb-5">
              Two autonomous AI agents, engineered for logic, precision, and adversarial reasoning — debating any topic in real time.
            </p>
            <motion.button 
              onClick={() => navigate('/dashboard')}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full bg-white/10 text-white font-['DM_Sans'] text-sm font-semibold py-2.5 rounded-full border border-white/20 transition-[background-color,color] duration-300 hover:bg-white hover:text-black will-change-transform transform-gpu"
            >
              Start Debate
            </motion.button>
          </GlassCard>
        </motion.div>

        {/* Right Bottom Card - Moved down more */}
        <motion.div 
          initial={{ opacity: 0, x: 30, y: 30 }}
          whileInView={{ opacity: 1, x: 0, y: 0 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.6, delay: 0.8 }}
          whileHover={{ y: -8, scale: 1.02 }}
          className="absolute bottom-[-40px] right-6 md:bottom-[-20px] md:right-10 lg:right-20 max-w-sm hidden lg:block z-40 cursor-default will-change-[transform,opacity] transform-gpu"
        >
          <GlassCard className="p-5 flex flex-col gap-3 border border-white/10 bg-black/40 before:backdrop-blur-xl">
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-lg overflow-hidden border border-white/20 shadow-[0_0_15px_rgba(255,255,255,0.1)]">
                <ImageWithFallback src={imgSingleThumb} alt="Judge Robot Thumbnail" className="w-full h-full object-cover" loading="lazy" decoding="async" />
              </div>
              <h3 className="font-['JetBrains_Mono'] text-[10px] font-bold text-white uppercase tracking-widest">
                Judge-0
              </h3>
            </div>
            <p className="font-['DM_Sans'] text-sm text-white/70 leading-relaxed">
              An impartial AI evaluator that scores arguments, detects fallacies, and delivers the final verdict.
            </p>
            <motion.button 
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full bg-white/10 text-white font-['DM_Sans'] text-sm font-semibold py-2.5 rounded-full transition-[background-color,color] duration-300 mt-1 border border-white/20 hover:bg-white hover:text-black will-change-transform transform-gpu"
            >
              Learn More
            </motion.button>
          </GlassCard>
        </motion.div>
      </div>
    </section>
  );
}