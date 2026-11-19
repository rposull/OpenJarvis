import { useCallback, useEffect, useId, useRef, useState } from 'react';

type TvSubscription = {
  subscribe: (obj: null, cb: () => void) => void;
  unsubscribe: (obj: null, cb: () => void) => void;
};

type TvActiveChart = {
  setSymbol?: (symbol: string, interval: string, callback?: () => void) => void;
  symbol?: () => string;
  onSymbolChanged?: () => TvSubscription;
};

type TvChartWidget = {
  remove?: () => void;
  onChartReady?: (callback: () => void) => void;
  setSymbol?: (symbol: string, interval: string, callback?: () => void) => void;
  activeChart?: () => TvActiveChart;
};

declare global {
  interface Window {
    TradingView?: {
      widget: (options: Record<string, unknown>) => TvChartWidget;
    };
  }
}

const TV_SCRIPT_ID = 'tradingview-widget-script';
const TV_SCRIPT_SRC = 'https://s3.tradingview.com/tv.js';

function loadTradingViewScript(): Promise<void> {
  if (window.TradingView) return Promise.resolve();
  const existing = document.getElementById(TV_SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return new Promise((resolve, reject) => {
      if (window.TradingView) {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', () => reject(new Error('TradingView script failed')));
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = TV_SCRIPT_ID;
    script.src = TV_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('TradingView script failed'));
    document.head.appendChild(script);
  });
}

function applyWidgetSymbol(
  widget: TvChartWidget,
  nextSymbol: string,
  nextInterval: string,
  onDone: () => void,
): boolean {
  const finish = () => onDone();

  if (typeof widget.setSymbol === 'function') {
    widget.setSymbol(nextSymbol, nextInterval, finish);
    return true;
  }

  const chart = widget.activeChart?.();
  if (typeof chart?.setSymbol === 'function') {
    chart.setSymbol(nextSymbol, nextInterval, finish);
    return true;
  }

  return false;
}

function readWidgetSymbol(widget: TvChartWidget): string | undefined {
  const chart = widget.activeChart?.();
  if (typeof chart?.symbol === 'function') {
    try {
      return chart.symbol();
    } catch {
      return undefined;
    }
  }
  return undefined;
}

interface TradingViewChartProps {
  symbol: string;
  interval?: string;
  theme?: 'light' | 'dark';
  height?: number | string;
  onSymbolChange?: (symbol: string) => void;
}

export function TradingViewChart({
  symbol,
  interval = '5',
  theme = 'dark',
  height = 640,
  onSymbolChange,
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<TvChartWidget | null>(null);
  const readyRef = useRef(false);
  const applyingExternalRef = useRef(false);
  const symbolRef = useRef(symbol);
  const onSymbolChangeRef = useRef(onSymbolChange);
  const symbolChangedHandlerRef = useRef<(() => void) | null>(null);
  const symbolChangedSubRef = useRef<TvSubscription | null>(null);
  const uid = useId().replace(/:/g, '');
  const containerId = `tradingview_${uid}`;

  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    onSymbolChangeRef.current = onSymbolChange;
  }, [onSymbolChange]);

  useEffect(() => {
    symbolRef.current = symbol;
  }, [symbol]);

  const teardownWidget = useCallback(() => {
    const widget = widgetRef.current;
    const handler = symbolChangedHandlerRef.current;
    const sub = symbolChangedSubRef.current;

    if (sub && handler) {
      try {
        sub.unsubscribe(null, handler);
      } catch {
        /* ignore */
      }
    }

    symbolChangedHandlerRef.current = null;
    symbolChangedSubRef.current = null;
    readyRef.current = false;
    widget?.remove?.();
    widgetRef.current = null;

    if (containerRef.current) {
      containerRef.current.innerHTML = '';
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const mount = async () => {
      const initialSymbol = symbolRef.current;
      if (!initialSymbol || !containerRef.current) return;

      setLoading(true);
      setLoadError('');
      readyRef.current = false;

      try {
        await loadTradingViewScript();
      } catch {
        if (!cancelled) {
          setLoadError('TradingView chart failed to load');
          setLoading(false);
        }
        return;
      }

      if (cancelled || !window.TradingView || !containerRef.current) return;

      teardownWidget();

      const el = document.createElement('div');
      el.id = containerId;
      el.style.height = '100%';
      el.style.width = '100%';
      containerRef.current.appendChild(el);

      const widget = window.TradingView.widget({
        autosize: true,
        width: '100%',
        height: '100%',
        symbol: initialSymbol,
        interval,
        timezone: 'Etc/UTC',
        theme,
        style: '1',
        locale: 'en',
        enable_publishing: false,
        allow_symbol_change: true,
        hide_side_toolbar: false,
        hide_top_toolbar: false,
        withdateranges: true,
        details: true,
        hotlist: true,
        calendar: true,
        studies: ['STD;EMA'],
        container_id: containerId,
        overrides: {
          'paneProperties.background': theme === 'dark' ? '#050818' : '#ffffff',
        },
      });

      widgetRef.current = widget;

      widget.onChartReady?.(() => {
        if (cancelled) return;

        readyRef.current = true;
        setLoading(false);

        const handler = () => {
          if (applyingExternalRef.current) return;

          const current = readWidgetSymbol(widget);
          if (!current || current === symbolRef.current) return;

          symbolRef.current = current;
          onSymbolChangeRef.current?.(current);
        };

        symbolChangedHandlerRef.current = handler;
        const sub = widget.activeChart?.()?.onSymbolChanged?.();
        if (sub) {
          symbolChangedSubRef.current = sub;
          sub.subscribe(null, handler);
        }

        const latest = symbolRef.current;
        const current = readWidgetSymbol(widget);
        if (latest && current !== latest) {
          setSwitching(true);
          applyingExternalRef.current = true;
          const applied = applyWidgetSymbol(widget, latest, interval, () => {
            applyingExternalRef.current = false;
            setSwitching(false);
          });
          if (!applied) {
            applyingExternalRef.current = false;
            setSwitching(false);
          }
        }
      });
    };

    void mount();

    return () => {
      cancelled = true;
      teardownWidget();
    };
  }, [theme, interval, containerId, teardownWidget]);

  useEffect(() => {
    if (!symbol || !readyRef.current) return;

    const widget = widgetRef.current;
    if (!widget) return;

    const current = readWidgetSymbol(widget);
    if (current === symbol) return;

    setSwitching(true);
    applyingExternalRef.current = true;

    const done = () => {
      applyingExternalRef.current = false;
      setSwitching(false);
    };

    const applied = applyWidgetSymbol(widget, symbol, interval, done);
    if (!applied) {
      done();
    }
  }, [symbol, interval]);

  const showOverlay = loading || switching;

  return (
    <div
      className="edith-tv-chart-wrap w-full rounded-lg overflow-hidden relative"
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        border: '1px solid var(--color-border)',
        background: '#050818',
      }}
    >
      <div ref={containerRef} className="w-full h-full" />

      {showOverlay && (
        <div className="edith-tv-chart-overlay" aria-live="polite">
          <div className="edith-tv-chart-spinner" aria-hidden />
          <span>{loading ? 'Loading chart…' : `Loading ${symbol}…`}</span>
        </div>
      )}

      {loadError && !loading && (
        <div className="edith-tv-chart-overlay edith-tv-chart-overlay-error">
          <span>{loadError}</span>
        </div>
      )}
    </div>
  );
}
