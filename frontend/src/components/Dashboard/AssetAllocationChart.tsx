import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { AllocationSlice } from '../../lib/dashboard/types';
import { CHART_COLORS } from '../../lib/dashboard/chartTheme';
import { HudPanel } from './HudPanel';

interface AssetAllocationChartProps {
  data: AllocationSlice[];
}

export function AssetAllocationChart({ data }: AssetAllocationChartProps) {
  return (
    <HudPanel title="Asset Allocation" subtitle="Portfolio mix" className="h-full">
      <div className="flex h-[200px] flex-col gap-3 sm:flex-row sm:items-center">
        <div className="h-[140px] flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                innerRadius={42}
                outerRadius={62}
                paddingAngle={3}
                stroke="rgba(0,0,0,0.4)"
              >
                {data.map((slice) => (
                  <Cell key={slice.name} fill={slice.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: CHART_COLORS.tooltipBg,
                  border: `1px solid ${CHART_COLORS.tooltipBorder}`,
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value) => [`${value}%`, 'Weight']}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex flex-1 flex-col gap-2 text-xs">
          {data.map((slice) => (
            <li key={slice.name} className="flex items-center justify-between gap-2 text-[var(--at-ink)]">
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: slice.color }} />
                {slice.name}
              </span>
              <span className="font-[family-name:var(--font-hud)] text-[var(--at-ink)]">{slice.value}%</span>
            </li>
          ))}
        </ul>
      </div>
    </HudPanel>
  );
}
