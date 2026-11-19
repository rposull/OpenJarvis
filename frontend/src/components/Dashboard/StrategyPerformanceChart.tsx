import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimeSeriesPoint } from '../../lib/dashboard/types';
import { CHART_COLORS, chartMargin } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface StrategyPerformanceChartProps {
  data: TimeSeriesPoint[];
  alphaIndex?: number;
}

export function StrategyPerformanceChart({ data, alphaIndex }: StrategyPerformanceChartProps) {
  const subtitle =
    alphaIndex != null
      ? `Alpha index ${alphaIndex.toFixed(1)} — live WR, return, signal & quality`
      : 'Alpha score index';
  return (
    <HudPanel title="Strategy Performance" subtitle={subtitle} className="h-full">
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={chartMargin}>
            <defs>
              <linearGradient id="strategyFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value) => [Number(value).toFixed(1), 'Score']}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#38bdf8"
              strokeWidth={2}
              fill="url(#strategyFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
