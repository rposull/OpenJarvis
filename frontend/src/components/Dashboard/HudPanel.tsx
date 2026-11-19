import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { cn } from '../../lib/utils';

interface HudPanelProps {
  title?: string;
  subtitle?: string;
  className?: string;
  children: ReactNode;
  noPadding?: boolean;
  accent?: boolean;
}

export function HudPanel({
  title,
  subtitle,
  className,
  children,
  noPadding = false,
  accent = false,
}: HudPanelProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={cn('at-panel h-full', accent && 'at-panel-accent', className)}
    >
      <span className="at-corner at-corner-tl" aria-hidden />
      <span className="at-corner at-corner-tr" aria-hidden />
      <span className="at-corner at-corner-bl" aria-hidden />
      <span className="at-corner at-corner-br" aria-hidden />

      {(title || subtitle) && (
        <header className="relative z-[1] border-b border-[rgba(200,245,66,0.12)] px-4 py-3">
          {title && (
            <h3 className="at-display text-[11px] font-semibold text-[var(--at-lime)]">
              {title}
            </h3>
          )}
          {subtitle && (
            <p className="mt-0.5 text-[11px] text-[var(--at-muted)]">{subtitle}</p>
          )}
        </header>
      )}

      <div className={cn('relative z-[1]', noPadding ? '' : 'p-4')}>{children}</div>
    </motion.section>
  );
}
