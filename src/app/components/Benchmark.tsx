import React from 'react';
import { GlassCard } from './GlassCard';

export function Benchmark() {
  const data = [
    { model: 'ARGUS-3 (ours)', args: 312, acc: '94.2%', lat: '0.8s', active: true },
    { model: 'GPT-4 Chain', args: 198, acc: '89.1%', lat: '2.1s', active: false },
    { model: 'LangGraph', args: 241, acc: '91.3%', lat: '1.4s', active: false },
  ];

  return (
    <section className="container mx-auto px-6 md:px-20 max-w-[1440px] flex flex-col items-center">
      
      <div className="flex flex-col items-center text-center mb-16">
        <span className="font-['JetBrains_Mono'] text-[10px] text-white/40 uppercase tracking-[0.2em] mb-4">
          Outperforming
        </span>
        <h2 className="font-['Orbitron'] text-4xl md:text-5xl font-bold text-white mb-3 tracking-wide">
          Fastest debate resolution engine
        </h2>
        <p className="font-['DM_Sans'] text-white/60 italic text-lg md:text-xl">
          Built for speed. Optimized for clarity.
        </p>
      </div>

      <GlassCard className="w-full max-w-4xl p-1 overflow-hidden">
        <div className="w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <table className="w-full text-left border-collapse min-w-[600px]">
            <thead>
              <tr className="bg-white/[0.03] border-b border-white/[0.08]">
                {['Model', 'Arguments/min', 'Accuracy', 'Latency'].map((th, i) => (
                  <th key={i} className="py-6 px-8 font-['JetBrains_Mono'] text-xs uppercase tracking-widest text-white/50 font-semibold">
                    {th}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} className={`border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors ${row.active ? 'bg-white/[0.04]' : ''}`}>
                  <td className="py-6 px-8">
                    <span className={`font-['JetBrains_Mono'] text-sm font-semibold ${row.active ? 'text-white' : 'text-white/70'}`}>
                      {row.model}
                    </span>
                  </td>
                  <td className={`py-6 px-8 font-['DM_Sans'] text-base ${row.active ? 'text-white font-medium' : 'text-white/70'}`}>
                    {row.args}
                  </td>
                  <td className={`py-6 px-8 font-['DM_Sans'] text-base ${row.active ? 'text-green-400 font-medium' : 'text-white/70'}`}>
                    {row.acc}
                  </td>
                  <td className={`py-6 px-8 font-['DM_Sans'] text-base ${row.active ? 'text-blue-400 font-medium' : 'text-white/70'}`}>
                    {row.lat}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

    </section>
  );
}
