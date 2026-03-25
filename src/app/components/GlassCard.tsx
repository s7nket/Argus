import React from 'react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';

export function GlassCard({ children, className, ...props }: React.ComponentProps<typeof motion.div>) {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={cn(
        'relative isolate contain-layout contain-paint will-change-transform transform-gpu',
        'bg-white/[0.05] border border-white/[0.08] hover:border-white/[0.15] transition-colors duration-300 rounded-[20px]',
        'shadow-[0_8px_32px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.06)]',
        'before:absolute before:inset-0 before:-z-10 before:rounded-[20px] before:backdrop-blur-[24px] before:backdrop-saturate-[180%] before:pointer-events-none',
        className
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}
