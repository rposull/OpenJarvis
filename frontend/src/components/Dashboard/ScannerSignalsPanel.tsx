import { motion } from 'motion/react';
import { ArrowDownRight, ArrowUpRight, Radar } from 'lucide-react';
import type { ScannerSignal } from '../../lib/dashboard/types';
import { HudPanel } from './HudPanel';

interface ScannerSignalsPanelProps {
  signals: ScannerSignal[];
}

function directionStyles(direction: ScannerSignal['direction']) {
  return direction === 'LONG'
    ? 'text-emerald-300 bg-emerald-500/10 border-emerald-400/30'
    : 'text-rose-300 bg-rose-500/10 border-rose-400/30';
}

export function ScannerSignalsPanel({ signals }: ScannerSignalsPanelProps) {
  return (
    <HudPanel title="Scanner Signals" subtitle="Live market scout feed" className="h-full">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {signals.length === 0 ? (
          <p className="col-span-full py-6 text-center text-sm text-[var(--at-muted)]">
            No active scout setups — start market scouts to populate signals.
          </p>
        ) : (
          signals.map((signal, index) => (
            <motion.article
              key={signal.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              whileHover={{ boxShadow: '0 0 20px rgba(200,245,66, 0.2)' }}
              className="rounded-xl border border-[rgba(200,245,66,0.2)] bg-black/30 p-3 backdrop-blur-md"
            >
              <div className="mb-3 flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <Radar className="h-4 w-4 text-[var(--at-lime)]" />
                    <span className="font-[family-name:var(--font-hud)] text-sm font-semibold text-[var(--at-ink)]">
                      {signal.ticker}
                    </span>
                  </div>
                  <span
                    className={`mt-1 inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${directionStyles(signal.direction)}`}
                  >
                    {signal.direction === 'LONG' ? (
                      <ArrowUpRight className="h-3 w-3" />
                    ) : (
                      <ArrowDownRight className="h-3 w-3" />
                    )}
                    {signal.direction}
                  </span>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase tracking-wider text-[var(--at-muted)]">Score</div>
                  <div className="text-lg font-semibold text-[var(--at-lime)]">{signal.score}</div>
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
                <div>
                  <dt className="text-[var(--at-muted)]">Entry</dt>
                  <dd className="text-[var(--at-ink)]">{signal.entry.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-[var(--at-muted)]">Status</dt>
                  <dd className="text-[var(--at-lime)]">{signal.status}</dd>
                </div>
                <div>
                  <dt className="text-[var(--at-muted)]">Stop Loss</dt>
                  <dd className="text-rose-200/90">{signal.stopLoss.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-[var(--at-muted)]">Take Profit</dt>
                  <dd className="text-emerald-200/90">{signal.takeProfit.toLocaleString()}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-[var(--at-muted)]">Risk / Reward</dt>
                  <dd className="font-[family-name:var(--font-hud)] text-[var(--at-ink)]">
                    1 : {signal.riskReward.toFixed(1)}
                  </dd>
                </div>
              </dl>
            </motion.article>
          ))
        )}
      </div>
    </HudPanel>
  );
}
