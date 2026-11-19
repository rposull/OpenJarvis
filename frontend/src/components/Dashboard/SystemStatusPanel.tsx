import { Activity, Server } from 'lucide-react';
import type { SystemStatusItem } from '../../lib/dashboard/types';
import { HudPanel } from './HudPanel';

interface SystemStatusPanelProps {
  items: SystemStatusItem[];
  lastUpdated: number;
}

const statusColor = {
  online: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]',
  degraded: 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.7)]',
  offline: 'bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.7)]',
} as const;

export function SystemStatusPanel({ items, lastUpdated }: SystemStatusPanelProps) {
  const stamp = new Date(lastUpdated).toLocaleTimeString();

  return (
    <HudPanel title="System Status" subtitle={`Last sync ${stamp}`}>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between rounded-lg border border-[rgba(200,245,66,0.15)] bg-black/25 px-3 py-2"
          >
            <div className="flex items-center gap-2 text-sm text-[var(--at-ink)]">
              {item.label === 'Inference' ? (
                <Activity className="h-4 w-4 text-[var(--at-lime)]" />
              ) : (
                <Server className="h-4 w-4 text-[var(--at-lime)]" />
              )}
              <span>{item.label}</span>
            </div>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-[var(--at-muted)]">
              {item.detail && <span className="hidden sm:inline">{item.detail}</span>}
              <span className={`h-2 w-2 rounded-full ${statusColor[item.status]}`} />
            </div>
          </div>
        ))}
      </div>
    </HudPanel>
  );
}
