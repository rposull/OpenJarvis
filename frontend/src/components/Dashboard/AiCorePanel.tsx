import { motion } from 'motion/react';
import { Activity, Zap } from 'lucide-react';
import { HudPanel } from './HudPanel';

interface AiCorePanelProps {
  status: 'online' | 'processing' | 'standby';
  load: number;
}

const statusLabel = {
  online: 'ARMED',
  processing: 'SYNCING',
  standby: 'IDLE',
} as const;

export function AiCorePanel({ status, load }: AiCorePanelProps) {
  return (
    <HudPanel title="Paper core" subtitle="Alpaca · local stack" accent className="h-full">
      <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-4 py-2">
        <div className="relative flex h-40 w-40 items-center justify-center">
          <svg viewBox="0 0 120 120" className="absolute inset-0 h-full w-full" aria-hidden>
            <defs>
              <linearGradient id="at-hex" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(200,245,66,0.55)" />
                <stop offset="100%" stopColor="rgba(255,179,71,0.25)" />
              </linearGradient>
            </defs>
            {[0, 1, 2].map((i) => (
              <motion.polygon
                key={i}
                points="60,8 104,34 104,86 60,112 16,86 16,34"
                fill="none"
                stroke="url(#at-hex)"
                strokeWidth={1}
                opacity={0.35 - i * 0.08}
                style={{ transformOrigin: '60px 60px', scale: 1 - i * 0.14 }}
                animate={{ rotate: i % 2 === 0 ? 360 : -360 }}
                transition={{ duration: 18 + i * 6, repeat: Infinity, ease: 'linear' }}
              />
            ))}
          </svg>
          <motion.div
            className="relative z-[1] flex h-20 w-20 items-center justify-center"
            style={{
              clipPath: 'polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)',
              background: 'rgba(200,245,66,0.12)',
              border: '1px solid rgba(200,245,66,0.45)',
              boxShadow: '0 0 32px rgba(200,245,66,0.25)',
            }}
            animate={{ scale: status === 'processing' ? [1, 1.05, 1] : [1, 1.02, 1] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          >
            <Activity className="h-8 w-8 text-[var(--at-lime)]" strokeWidth={1.5} />
          </motion.div>
        </div>

        <div className="text-center">
          <div className="at-display text-sm font-semibold text-[var(--at-lime)]">Alpaca</div>
          <div className="mt-1 flex items-center justify-center gap-2 text-xs text-[var(--at-muted)]">
            <span
              className={`inline-block h-2 w-2 ${
                status === 'online'
                  ? 'bg-[var(--at-lime)] shadow-[0_0_8px_rgba(200,245,66,0.8)]'
                  : status === 'processing'
                    ? 'bg-[var(--at-amber)] shadow-[0_0_8px_rgba(255,179,71,0.8)]'
                    : 'bg-[var(--at-muted)]'
              }`}
              style={{ clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)' }}
            />
            {statusLabel[status]}
          </div>
        </div>

        <div className="w-full max-w-[200px]">
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-[var(--at-muted)]">
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3 text-[var(--at-amber)]" />
              Stack load
            </span>
            <span className="text-[var(--at-lime)]">{load}%</span>
          </div>
          <div className="h-1.5 overflow-hidden bg-black/50" style={{ borderRadius: 1 }}>
            <motion.div
              className="h-full"
              style={{
                background: 'linear-gradient(90deg, #c8f542, #ffb347)',
                borderRadius: 1,
              }}
              animate={{ width: `${load}%` }}
              transition={{ duration: 0.55 }}
            />
          </div>
        </div>
      </div>
    </HudPanel>
  );
}
