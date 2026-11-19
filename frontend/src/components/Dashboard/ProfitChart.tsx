import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimeSeriesPoint } from '../../lib/dashboard/types';
import { CHART_COLORS, chartMargin } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface ProfitChartProps {
  data: TimeSeriesPoint[];
}

export function ProfitChart({ data }: ProfitChartProps) {
  return (
    <HudPanel title="Profit" subtitle="Session P&L timeline" className="h-full">
      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={chartMargin}>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={42} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: CHART_COLORS.cyan }}
              formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Profit']}
            />
            <Bar dataKey="value" fill={CHART_COLORS.cyan} radius={[4, 4, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
