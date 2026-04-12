import React, { useState } from 'react';
import { motion, useInView } from 'motion/react';
import { GlassCard } from './GlassCard';

export function ModelsSupported() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const [activeTab, setActiveTab] = useState('All');
  
  const tabs = ['All', 'Gemini', 'GPT-4o', 'Claude', 'Mistral', 'LLaMA'];
  
  const models = [
    { name: 'GPT-4o', provider: 'OpenAI', type: 'Cloud', active: true },
    { name: 'Claude 3.5 Sonnet', provider: 'Anthropic', type: 'Cloud', active: true },
    { name: 'Gemini 1.5 Pro', provider: 'Google', type: 'Cloud', active: true },
    { name: 'Llama 3 70B', provider: 'Meta', type: 'Local', active: true },
    { name: 'Mistral Large', provider: 'Mistral AI', type: 'Local / Cloud', active: true },
    { name: 'Custom Model', provider: 'Your Infra', type: 'Any', active: true },
  ];

  return (
    <section ref={ref} className="container mx-auto px-6 md:px-20 max-w-[1440px] flex flex-col items-center">
      
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center text-center mb-10 will-change-[transform,opacity] transform-gpu"
      >
        <h2 className="font-['Orbitron'] text-2xl md:text-3xl font-bold text-white mb-3 tracking-wide">
          All key LLMs supported
        </h2>
        <p className="font-['DM_Sans'] text-white/60 text-base mb-8">
          Pick your model. Start your debate.
        </p>
        
        <button className="mb-10 flex items-center gap-2 px-6 py-2 rounded-full border border-white/20 bg-white/10 text-white hover:bg-white hover:text-black transition-colors duration-300 font-['JetBrains_Mono'] text-xs font-bold tracking-widest uppercase shadow-[0_0_15px_rgba(255,255,255,0.1)] will-change-transform transform-gpu">
          Begin &rarr;
        </button>
        
        {/* Tabs */}
        <div className="flex flex-wrap justify-center gap-3">
          {tabs.map(tab => (
            <button 
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2 rounded-full font-['JetBrains_Mono'] text-xs font-semibold transition-colors duration-200 ${
                activeTab === tab 
                  ? 'bg-white text-black border border-white' 
                  : 'bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 hover:text-white'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Grid */}
      <div className="models-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 w-full max-w-5xl mt-8">
        {models.map((model, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ duration: 0.4, delay: 0.1 + i * 0.05 }}
            className="model-card will-change-[transform,opacity] transform-gpu"
          >
            <GlassCard className="p-6 flex flex-col gap-4">
              <div className="flex justify-between items-start">
                <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center border border-white/5">
                  {/* Logo Placeholder */}
                  <div className="w-5 h-5 rounded-sm bg-white/20" />
                </div>
                <GlassCard className="px-2 py-1 text-center flex items-center justify-center">
                  <span className="font-['JetBrains_Mono'] text-[10px] text-white/50 uppercase">
                    {model.type}
                  </span>
                </GlassCard>
              </div>
              <div>
                <h4 className="font-['DM_Sans'] text-base font-bold text-white mb-1">{model.name}</h4>
                <p className="font-['JetBrains_Mono'] text-xs text-white/40">{model.provider}</p>
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

    </section>
  );
}