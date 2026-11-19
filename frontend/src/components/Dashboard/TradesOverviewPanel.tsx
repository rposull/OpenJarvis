import { motion } from 'motion/react';
import { ArrowDownRight, ArrowUpRight, Clock, History, Wallet } from 'lucide-react';
import type { ClosedTradeRow, OpenTradeRow, PendingExecution } from '../../lib/dashboard/types';
import { HudPanel } from './HudPanel';

function pendingStyles(status: PendingExecution['status']) {
  switch (status) {
    case 'READY':
      return 'text-emerald-300 bg-emerald-500/15 border-emerald-400/40';
    case 'NEAR':
      return 'text-amber-200 bg-amber-500/10 border-amber-400/35';
    case 'BLOCKED':
      return 'text-rose-300 bg-rose-500/10 border-rose-400/30';
    default:
      return 'text-[var(--at-lime)] bg-[rgba(200,245,66,0.1)] border-[rgba(200,245,66,0.25)]';
  }
}

interface TradesOverviewPanelProps {
  openTrades: OpenTradeRow[];
  closedTrades: ClosedTradeRow[];
  pendingExecutions: PendingExecution[];
  strategyDisplay?: boolean;
}

export function TradesOverviewPanel({
  openTrades,
  closedTrades,
  pendingExecutions,
  strategyDisplay = false,
}: TradesOverviewPanelProps) {
  const ready = pendingExecutions.filter((p) => p.status === 'READY');
  const near = pendingExecutions.filter((p) => p.status === 'NEAR');

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <HudPanel
        title="Open Trades"
        subtitle={`${openTrades.length} position${openTrades.length === 1 ? '' : 's'} live`}
        className="min-h-[280px]"
      >
        {openTrades.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--at-muted)]">No open positions.</p>
        ) : (
          <ul className="space-y-2">
            {openTrades.map((t, i) => (
              <motion.li
                key={t.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className="rounded-xl border border-[rgba(200,245,66,0.2)] bg-black/30 px-3 py-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <Wallet className="h-3.5 w-3.5 text-[var(--at-lime)]" />
                      <span className="font-[family-name:var(--font-hud)] text-sm font-semibold text-[var(--at-ink)]">
                        {t.symbol}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[var(--at-muted)]">{t.qty}</p>
                  </div>
                  <div className="text-right text-[11px]">
                    <div className="text-[var(--at-muted)]">Worth now</div>
                    <div className="font-semibold text-[var(--at-ink)]">
                      ${(t.marketValueUsd ?? t.entryCostUsd ?? t.entryPrice).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                    <div className="mt-0.5 text-[var(--at-muted)]">
                      paid ${(t.entryCostUsd ?? t.entryPrice).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                    {t.pnl != null ? (
                      <div
                        className={`mt-1 font-medium ${t.pnl >= 0 ? 'text-emerald-200/90' : 'text-rose-300/90'}`}
                      >
                        {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)} uPnL
                      </div>
                    ) : t.unrealized ? (
                      <div className="mt-1 font-medium text-emerald-200/90">{t.unrealized}</div>
                    ) : null}
                  </div>
                </div>
                {t.note && <p className="mt-1 truncate text-[10px] text-[var(--at-muted)]">{t.note}</p>}
              </motion.li>
            ))}
          </ul>
        )}
      </HudPanel>

      <HudPanel
        title="Closed Trades"
        subtitle={
          strategyDisplay
            ? `${closedTrades.length} strategy book · updates every 5s`
            : `${closedTrades.length} all-time`
        }
        className="min-h-[280px]"
      >
        {closedTrades.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--at-muted)]">No closed trades yet.</p>
        ) : (
          <ul className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {closedTrades.slice().reverse().map((t, i) => (
              <motion.li
                key={t.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="rounded-xl border border-[rgba(200,245,66,0.15)] bg-black/25 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <History className="h-3.5 w-3.5 text-[var(--at-lime)]" />
                    <span className="text-sm font-medium text-[var(--at-ink)]">{t.symbol}</span>
                  </div>
                  <span
                    className={`text-sm font-semibold ${t.pnl >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}
                  >
                    {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-[var(--at-muted)]">
                  {t.exitReason || t.note || 'closed'}
                </p>
              </motion.li>
            ))}
          </ul>
        )}
      </HudPanel>

      <HudPanel
        title="Pending Execution"
        subtitle={`${ready.length} ready · ${near.length} near threshold`}
        className="min-h-[280px]"
      >
        {pendingExecutions.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--at-muted)]">
            No scout setups — auto-buy fires at score + conviction gates.
          </p>
        ) : (
          <ul className="space-y-2">
            {pendingExecutions.map((p, i) => (
              <motion.li
                key={p.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className="rounded-xl border border-[rgba(200,245,66,0.2)] bg-black/30 px-3 py-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <Clock className="h-3.5 w-3.5 text-[var(--at-lime)]" />
                      <span className="font-[family-name:var(--font-hud)] text-sm font-semibold text-[var(--at-ink)]">
                        {p.ticker}
                      </span>
                      <span
                        className={`inline-flex items-center gap-0.5 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase ${pendingStyles(p.status)}`}
                      >
                        {p.direction === 'LONG' ? (
                          <ArrowUpRight className="h-3 w-3" />
                        ) : (
                          <ArrowDownRight className="h-3 w-3" />
                        )}
                        {p.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[10px] text-[var(--at-muted)]">{p.gapLabel}</p>
                  </div>
                  <div className="text-right text-[11px]">
                    <div className="text-[var(--at-muted)]">Score</div>
                    <div className="text-[var(--at-ink)]">{p.score}%</div>
                    {p.convictionPct != null && (
                      <div className="mt-0.5 text-[var(--at-muted)]">Conv {p.convictionPct}%</div>
                    )}
                  </div>
                </div>
              </motion.li>
            ))}
          </ul>
        )}
      </HudPanel>
    </div>
  );
}
