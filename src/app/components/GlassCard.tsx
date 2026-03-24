import React from 'react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';

export function GlassCard({ children, className, ...props }: React.ComponentProps<typeof motion.div>) {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={cn(
        'bg-white/[0.05] backdrop-blur-[24px] backdrop-saturate-[180%] border border-white/[0.08] hover:border-white/[0.15] transition-colors duration-300 rounded-[20px]',
        'shadow-[0_8px_32px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.06)]',
        className
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}
