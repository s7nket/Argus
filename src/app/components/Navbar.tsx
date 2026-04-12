import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';
import { Triangle } from 'lucide-react';
import { useNavigate } from 'react-router';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let ticking = false;
    const handleScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          setScrolled(window.scrollY > 80);
          ticking = false;
        });
        ticking = true;
      }
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
        'fixed top-0 left-0 right-0 z-50 h-20 transition-[background-color,border-color] duration-300 flex items-center will-change-transform transform-gpu',
        scrolled ? 'bg-black/40 before:absolute before:inset-0 before:-z-10 before:backdrop-blur-3xl border-b border-white/[0.06] isolate' : 'bg-transparent border-b border-transparent'
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
                <span className="relative flex h-2 w-2 isolate">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75 will-change-[transform,opacity] transform-gpu"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
                </span>
              )}
              {item}
            </a>
          ))}
        </div>

        {/* Right CTA */}
        <button onClick={() => navigate('/debate-dashboard')} className="hidden md:flex items-center justify-center px-6 py-2.5 rounded-full bg-white text-black font-['DM_Sans'] text-sm font-medium hover:bg-black hover:text-white border border-transparent hover:border-white transition-colors duration-300 will-change-transform transform-gpu">
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
