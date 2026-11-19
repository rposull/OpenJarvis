import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { VolumeBar } from '../../lib/dashboard/types';
import { CHART_COLORS, chartMargin } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface VolumeAnalysisChartProps {
  data: VolumeBar[];
}

export function VolumeAnalysisChart({ data }: VolumeAnalysisChartProps) {
  return (
    <HudPanel title="Volume Analysis" subtitle="Symbol liquidity scan" className="h-full">
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ ...chartMargin, bottom: 4 }}>
            <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={48} />
            <Tooltip
              contentStyle={{
                background: CHART_COLORS.tooltipBg,
                border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value) => [Number(value).toLocaleString(), 'Volume']}
            />
            <Bar dataKey="volume" fill={CHART_COLORS.cyanDim} stroke={CHART_COLORS.cyan} strokeWidth={1} radius={[4, 4, 0, 0]} maxBarSize={36} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
}
