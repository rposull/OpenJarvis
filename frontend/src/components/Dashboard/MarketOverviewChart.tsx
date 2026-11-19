import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimeSeriesPoint } from '../../lib/dashboard/types';
import { CHART_COLORS, chartMargin } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface MarketOverviewChartProps {
  data: TimeSeriesPoint[];
}

export function MarketOverviewChart({ data }: MarketOverviewChartProps) {
  return (
    <HudPanel title="Market Overview" subtitle="Price + volume composite" className="h-full">
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={chartMargin}>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="price" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={42} />
            <YAxis yAxisId="volume" orientation="right" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Bar yAxisId="volume" dataKey="volume" fill={CHART_COLORS.cyanDim} radius={[2, 2, 0, 0]} maxBarSize={16} />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="value"
              stroke={CHART_COLORS.cyan}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: CHART_COLORS.cyan }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
