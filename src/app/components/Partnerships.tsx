import React from 'react';
import { ArrowRight } from 'lucide-react';

export function Partnerships() {
  return (
    <section className="container mx-auto px-6 md:px-20 py-10 flex flex-col items-center justify-center text-center">
      <div className="font-['JetBrains_Mono'] text-xs text-white/50 tracking-widest uppercase mb-4">
        ARGUS × Open Ecosystem
      </div>
      
      <p className="font-['DM_Sans'] text-lg md:text-xl text-white/60 mb-8 max-w-lg leading-relaxed">
        Built on open-source LLM infrastructure. Integrates with your existing AI stack.
      </p>

      <button className="flex items-center gap-2 px-6 py-2.5 rounded-full bg-white/5 border border-white/10 text-white/80 font-['DM_Sans'] text-sm hover:bg-white/10 hover:text-white transition-all">
        Explore Integrations <ArrowRight className="w-4 h-4" />
      </button>
    </section>
  );
}
