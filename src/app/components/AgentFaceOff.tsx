import React from 'react';
import { motion, useInView } from 'motion/react';
import { GlassCard } from './GlassCard';
import { Check } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';

import { useNavigate } from 'react-router';

import imgLayout2 from '../../assets/layout2.png';

export function AgentFaceOff() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const navigate = useNavigate();

  const points = [
    'Sub-second argument generation',
    'Transparent scoring per round',
    'Full winning argument breakdown'
  ];

  return (
    <section ref={ref} className="container mx-auto px-6 md:px-20 max-w-[1440px] py-16 md:py-24 overflow-hidden">
      
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7 }}
        className="will-change-[transform,opacity] transform-gpu"
      >
        <GlassCard className="w-full flex flex-col md:flex-row-reverse items-stretch border border-white/10 shadow-2xl p-0 overflow-hidden">
          
          {/* Left Image */}
          <div className="w-full md:w-1/2 relative bg-white/5 flex items-center justify-center overflow-hidden">
            <ImageWithFallback 
              src={imgLayout2} 
              alt="Agent Face Off Background" 
              className="w-full h-full min-h-[400px] object-cover object-center scale-105 hover:scale-110 transition-transform duration-700 ease-out will-change-transform transform-gpu"
              loading="lazy"
              decoding="async"
            />
          </div>

          {/* Right Content */}
          <div className="w-full md:w-1/2 p-8 md:p-12 lg:p-16 flex flex-col justify-center">
            <h2 className="font-['Orbitron'] text-2xl md:text-3xl font-bold text-white leading-tight mb-5">
              Users don't care who wins.<br/>
              <span className="text-white/50">They care how it's argued.</span>
            </h2>
            
            <p className="font-['DM_Sans'] text-sm md:text-base text-white/80 leading-relaxed mb-8">
              ARGUS delivers debate-native experiences — fast, structured, and brutally fair.
            </p>
            
            <ul className="space-y-3.5 mb-8">
              {points.map((point, i) => (
                <li key={i} className="flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-white/10 border border-white/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Check className="w-3 h-3 text-white" />
                  </div>
                  <span className="font-['JetBrains_Mono'] text-xs md:text-sm text-white/70">{point}</span>
                </li>
              ))}
            </ul>
            
            <button onClick={() => navigate('/dashboard')} className="bg-white text-black font-['DM_Sans'] text-sm md:text-base font-bold py-3 px-7 rounded-full hover:bg-black hover:text-white border-2 border-transparent hover:border-white transition-colors duration-300 shadow-[0_0_20px_rgba(255,255,255,0.2)] w-fit will-change-[transform,opacity] transform-gpu">
              Start the Face-Off &rarr;
            </button>
          </div>
        </GlassCard>
      </motion.div>

    </section>
  );
}