import { useEffect, useRef } from 'react';
import {
  ColorType,
  createChart,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { SetupChartPayload } from '../../lib/api';

interface SetupCandleChartProps {
  data: SetupChartPayload | null;
  height?: number;
}

export function SetupCandleChart({ data, height = 420 }: SetupCandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !data?.ok || !data.candles?.length) return;

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'rgba(8, 12, 22, 0.95)' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
      },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.2)' },
      timeScale: { borderColor: 'rgba(148, 163, 184, 0.2)', timeVisible: true },
      crosshair: { mode: 1 },
      width: el.clientWidth,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    candleSeries.setData(
      data.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    if (data.lines?.ema9?.length) {
      const s9 = chart.addLineSeries({ color: '#38bdf8', lineWidth: 1, title: 'EMA9' });
      s9.setData(data.lines.ema9.map((p) => ({ time: p.time as Time, value: p.value })));
    }
    if (data.lines?.ema21?.length) {
      const s21 = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1, title: 'EMA21' });
      s21.setData(data.lines.ema21.map((p) => ({ time: p.time as Time, value: p.value })));
    }

    for (const ov of data.overlays || []) {
      if (ov.kind === 'fvg' && ov.top != null && ov.bottom != null) {
        candleSeries.createPriceLine({
          price: ov.top,
          color: ov.color || '#a78bfa',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${ov.label || 'FVG'} top`,
        });
        candleSeries.createPriceLine({
          price: ov.bottom,
          color: ov.color || '#a78bfa',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${ov.label || 'FVG'} bot`,
        });
      } else if (ov.price != null) {
        candleSeries.createPriceLine({
          price: ov.price,
          color: ov.color || '#22d3ee',
          lineWidth: ov.kind === 'stop' ? 2 : 1,
          lineStyle: ov.kind === 'fib' || ov.kind === 'fib_active' ? 2 : 0,
          axisLabelVisible: true,
          title: ov.label || ov.kind || 'level',
        });
      }
    }

    const markers: SeriesMarker<Time>[] = (data.markers || []).map((m) => ({
      time: m.time as Time,
      position: m.position,
      shape: m.shape,
      color: m.color,
      text: m.text,
    }));
    if (markers.length) {
      candleSeries.setMarkers(markers);
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [data, height]);

  if (!data?.ok) {
    return (
      <div
        className="flex items-center justify-center rounded border border-white/10 bg-black/30 text-sm edith-subtitle"
        style={{ height }}
      >
        {data?.error || 'Select a setup to load chart'}
      </div>
    );
  }

  return (
    <div className="rounded border border-white/10 overflow-hidden bg-black/30">
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
