import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimeSeriesPoint } from '../../lib/dashboard/types';
import { CHART_COLORS, chartMargin } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface WinRateChartProps {
  data: TimeSeriesPoint[];
  wins?: number;
  losses?: number;
  breakeven?: number;
}

export function WinRateChart({ data, wins = 0, losses = 0, breakeven = 0 }: WinRateChartProps) {
  const decisive = wins + losses;
  const latest = data.length ? data[data.length - 1].value : 0;
  const yMin = Math.max(0, Math.floor(Math.min(latest, ...data.map((d) => d.value)) / 10) * 10 - 10);
  const subtitle = decisive
    ? `${wins} wins · ${losses} losses${breakeven ? ` · ${breakeven} breakeven` : ''} · cumulative after each close`
    : 'No closed trades yet';

  return (
    <HudPanel title="Win Rate" subtitle={subtitle} className="h-full">
      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={chartMargin}>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis domain={[yMin, 100]} tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Win Rate']}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={CHART_COLORS.cyan}
              strokeWidth={2}
              dot={{ r: 2, fill: CHART_COLORS.cyan }}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
