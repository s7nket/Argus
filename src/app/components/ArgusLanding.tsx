import React from 'react';
import { motion } from 'motion/react';
import { Navbar } from './Navbar';
import { Hero } from './Hero';
import { HowItWorks } from './HowItWorks';
import { DebateInAction } from './DebateInAction';
import { ResultsAndVerdict } from './ResultsAndVerdict';
import { ModelsSupported } from './ModelsSupported';
import { AgentFaceOff } from './AgentFaceOff';
import { FooterHero } from './FooterHero';

export function ArgusLanding() {
  return (
    <div className="relative min-h-screen bg-[#050505] text-white font-sans overflow-x-hidden selection:bg-white/20 selection:text-white">
      {/* Background Gradient */}
      <div className="fixed inset-0 pointer-events-none bg-gradient-to-b from-[#050505] to-[#0a0a0f] z-[-60]" />
      
      {/* Grid Overlay */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.03 }}
        transition={{ delay: 1, duration: 1.5 }}
        className="fixed inset-0 pointer-events-none z-[-40]"
        style={{
          backgroundImage: 'linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)',
          backgroundSize: '80px 80px'
        }}
      />

      <Navbar />
      
      <main className="flex flex-col gap-16 md:gap-24 pb-12 md:pb-20">
        <Hero />
        <HowItWorks />
        <ResultsAndVerdict />
        <DebateInAction />
        <ModelsSupported />
        <AgentFaceOff />
        <FooterHero />
      </main>
    </div>
  );
}