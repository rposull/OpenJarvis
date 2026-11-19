import { motion } from 'motion/react';
import { Activity, Bot, CircleDollarSign, Percent, TrendingUp, Wallet } from 'lucide-react';
import type { DashboardStats } from '../../lib/dashboard/types';

interface StatsPanelProps {
  stats: DashboardStats;
}

function closedLabel(stats: DashboardStats): string {
  return stats.strategyDisplay ? 'Closed (strategy)' : 'Closed (all)';
}

function buildCards(stats: DashboardStats): {
  key: keyof DashboardStats;
  label: string;
  icon: typeof Activity;
  format: (s: DashboardStats) => string;
}[] {
  return [
    {
      key: 'equity',
      label: 'Equity',
      icon: CircleDollarSign,
      format: (s) =>
        `$${s.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    },
    {
      key: 'profit',
      label: 'PnL',
      icon: TrendingUp,
      format: (s) => {
        const u =
          s.unrealizedPnl !== 0
            ? ` · u${s.unrealizedPnl >= 0 ? '+' : ''}$${Math.abs(s.unrealizedPnl).toFixed(0)}`
            : '';
        return `$${s.profit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${u}`;
      },
    },
    {
      key: 'winRate',
      label: 'Win Rate',
      icon: Percent,
      format: (s) => {
        const decisive = s.wins + s.losses;
        if (!decisive) return `${s.winRate.toFixed(1)}%`;
        const parts = [`${s.wins}W`, `${s.losses}L`];
        if (s.breakeven > 0) parts.push(`${s.breakeven}BE`);
        return `${s.winRate.toFixed(1)}% · ${parts.join(' · ')}`;
      },
    },
    {
      key: 'openTrades',
      label: 'Open',
      icon: Wallet,
      format: (s) => String(s.openTrades),
    },
    {
      key: 'closedTrades',
      label: closedLabel(stats),
      icon: Activity,
      format: (s) => String(s.closedTrades),
    },
    {
      key: 'pendingExecutions',
      label: 'Pending',
      icon: Bot,
      format: (s) => String(s.pendingExecutions),
    },
  ];
}

export function StatsPanel({ stats }: StatsPanelProps) {
  const items = buildCards(stats);
  return (
    <div className="grid h-full grid-cols-2 gap-3 md:grid-cols-3">
      {items.map((card, index) => (
        <motion.div
          key={card.key}
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: index * 0.04, duration: 0.28 }}
          className="at-stat"
        >
          <card.icon className="mb-1.5 h-4 w-4 text-[var(--at-lime)] opacity-80" strokeWidth={1.5} />
          <div className="at-display text-[9px] text-[var(--at-muted)]">{card.label}</div>
          <div className="at-stat-value mt-1 max-w-full truncate">{card.format(stats)}</div>
        </motion.div>
      ))}
    </div>
  );
}
