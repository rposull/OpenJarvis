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

interface EquityCurveChartProps {
  data: TimeSeriesPoint[];
  equity?: number;
}

export function EquityCurveChart({ data, equity }: EquityCurveChartProps) {
  const subtitle =
    equity != null
      ? `Live equity $${equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
      : 'Portfolio growth';
  return (
    <HudPanel title="Equity Curve" subtitle={subtitle} className="h-full">
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={chartMargin}>
            <defs>
              <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.cyan} stopOpacity={0.35} />
                <stop offset="100%" stopColor={CHART_COLORS.cyan} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={52} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Equity']}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={CHART_COLORS.cyan}
              strokeWidth={2}
              fill="url(#equityFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
