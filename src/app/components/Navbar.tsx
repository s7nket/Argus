import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';
import { Triangle } from 'lucide-react';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 80);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <motion.nav
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className={cn(
        'fixed top-0 left-0 right-0 z-50 h-20 transition-all duration-300 flex items-center',
        scrolled ? 'bg-black/40 backdrop-blur-3xl border-b border-white/[0.06]' : 'bg-transparent backdrop-blur-none border-b border-transparent'
      )}
    >
      <div className="container mx-auto px-6 md:px-20 max-w-[1440px] flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <Triangle className="w-5 h-5 fill-white text-white rotate-180" />
          <span className="font-['Orbitron'] font-bold text-xl tracking-wider uppercase">Argus</span>
        </div>

        {/* Center Links (Desktop) */}
        <div className="hidden md:flex items-center gap-8">
          {['DEBATE', 'AGENTS'].map((item) => (
            <a key={item} href="#" className={cn("font-['JetBrains_Mono'] text-xs uppercase tracking-widest transition-colors flex items-center gap-2", item === 'DEBATE' ? "text-white/90 hover:text-white" : "text-white/60 hover:text-white/90")}>
              {item === 'DEBATE' && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
                </span>
              )}
              {item}
            </a>
          ))}
        </div>

        {/* Right CTA */}
        <button className="hidden md:flex items-center justify-center px-6 py-2.5 rounded-full bg-white text-black font-['DM_Sans'] text-sm font-medium hover:bg-black hover:text-white border border-transparent hover:border-white transition-all">
          Live Debate
        </button>

        {/* Mobile Hamburger (placeholder) */}
        <button className="md:hidden flex flex-col gap-1.5 p-2 text-white">
          <div className="w-5 h-[2px] bg-white"></div>
          <div className="w-5 h-[2px] bg-white"></div>
        </button>
      </div>
    </motion.nav>
  );
}
