import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  ArrowDownRight,
  ArrowUpRight,
  CandlestickChart,
  ExternalLink,
  RefreshCw,
  ScanSearch,
  TrendingUp,
} from 'lucide-react';
import { SetupCandleChart } from '../components/Trading/SetupCandleChart';
import { TradingViewChart } from '../components/Trading/TradingViewChart';
import { TradingViewLinkPanel } from '../components/Trading/TradingViewLinkPanel';
import {
  fetchSetupChart,
  fetchSetupScanner,
  fetchTradingViewLink,
  type SetupChartPayload,
  type SetupScannerRow,
  type TradingViewLinkStatus,
} from '../lib/api';
import '../styles/trading-edith.css';

function fmtPct(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  const v = n <= 1 ? n * 100 : n;
  return `${v.toFixed(0)}%`;
}

function directionIcon(dir?: string) {
  return String(dir || '').toLowerCase() === 'short' ? (
    <ArrowDownRight size={14} className="text-rose-400" />
  ) : (
    <ArrowUpRight size={14} className="text-emerald-400" />
  );
}

export function SetupScannerPage() {
  const [rows, setRows] = useState<SetupScannerRow[]>([]);
  const [selected, setSelected] = useState<SetupScannerRow | null>(null);
  const [chart, setChart] = useState<SetupChartPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState('');

  const [filter, setFilter] = useState<'all' | 'entry' | 'chart'>('all');
  const [chartMode, setChartMode] = useState<'jarvis' | 'tradingview'>('jarvis');
  const [tvLink, setTvLink] = useState<TradingViewLinkStatus | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchSetupScanner();
      const setups = data.setups || [];
      setRows(setups);
      setSelected((prev) => {
        if (!setups.length) return null;
        if (!prev) return setups[0];
        const key = `${prev.symbol}:${prev.pattern || ''}`;
        return setups.find((r) => `${r.symbol}:${r.pattern || ''}` === key) || setups[0];
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load scans');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadChart = useCallback(async (row: SetupScannerRow) => {
    setChartLoading(true);
    try {
      const payload = await fetchSetupChart(row.symbol, row.pattern);
      setChart(payload);
    } catch (e) {
      setChart({ ok: false, symbol: row.symbol, error: e instanceof Error ? e.message : 'Chart failed' });
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 20000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    fetchTradingViewLink()
      .then(setTvLink)
      .catch(() => setTvLink(null));
  }, []);

  useEffect(() => {
    if (selected?.symbol) {
      void loadChart(selected);
    }
  }, [selected, loadChart]);

  const trend = chart?.trend;
  const setup = chart?.setup;
  const visibleRows = rows.filter((row) => {
    if (filter === 'entry') return row.entry_allowed === true;
    if (filter === 'chart') return row.chart_ready !== false;
    return true;
  });
  const entryCount = rows.filter((r) => r.entry_allowed).length;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10 edith-trading">
      <div className="cosmos-layer cosmos-nebula" aria-hidden />
      <div className="cosmos-layer cosmos-aurora" aria-hidden />
      <div className="cosmos-layer cosmos-stars" aria-hidden />

      <div className="relative z-10 max-w-7xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-xl font-semibold edith-value tracking-wide flex items-center gap-2">
              <ScanSearch size={22} style={{ color: 'var(--edith-cyan)' }} />
              Setup Scanner
            </h1>
            <p className="text-sm edith-subtitle mt-1 max-w-2xl">
              Posted scout scans with candlesticks, EMA trend lines, S/R · FVG · Fib overlays, and
              entry / exit markers from your book.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/trading" className="edith-btn edith-btn-sm edith-btn-ghost">
              Trading
            </Link>
            <Link to="/hedge-fund" className="edith-btn edith-btn-sm edith-btn-ghost">
              Hedge Fund
            </Link>
            <button type="button" className="edith-btn edith-btn-sm edith-btn-ghost" onClick={() => refresh()} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="edith-panel mb-4 p-3 text-sm text-rose-400 border border-rose-500/30">{error}</div>
        )}

        <div className="mb-4">
          <TradingViewLinkPanel compact />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-4">
          <section className="edith-panel edith-scan-wrap p-3 max-h-[780px] overflow-y-auto">
            <div className="jarvis-scan-line" aria-hidden />
            <h2 className="text-xs edith-label uppercase tracking-wider mb-2 flex items-center gap-2">
              <CandlestickChart size={14} />
              Posted scans ({visibleRows.length}/{rows.length})
            </h2>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {(
                [
                  ['all', `All (${rows.length})`],
                  ['entry', `Entry ok (${entryCount})`],
                  ['chart', 'Has chart'],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`text-[10px] px-2 py-0.5 rounded border ${
                    filter === id ? 'border-cyan-500/50 text-cyan-300' : 'border-white/10 edith-subtitle'
                  }`}
                  onClick={() => setFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            {visibleRows.length === 0 && !loading ? (
              <p className="text-xs edith-subtitle">No setups match filter.</p>
            ) : (
              <ul className="space-y-2">
                {visibleRows.map((row) => {
                  const active = selected?.symbol === row.symbol && selected?.pattern === row.pattern;
                  const conf = row.signal_score ?? (row.confidence != null ? row.confidence * 100 : null);
                  const isTvAlert = row.scan_source === 'tradingview_alert';
                  const tvChartUrl =
                    row.chart_url ||
                    (row.tradingview_symbol
                      ? `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(row.tradingview_symbol)}`
                      : '');
                  return (
                    <li key={`${row.symbol}-${row.pattern}-${row.scan_source}-${row.received_at ?? ''}`}>
                      <button
                        type="button"
                        onClick={() => setSelected(row)}
                        className={`w-full text-left px-3 py-2 rounded border transition-colors ${
                          active
                            ? 'border-cyan-500/50 bg-cyan-500/10'
                            : 'border-white/10 hover:border-white/20 bg-white/5'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm edith-value font-medium flex items-center gap-1">
                            {directionIcon(row.direction)}
                            {row.symbol}
                          </span>
                          <span className="text-[10px] edith-subtitle flex items-center gap-1">
                            {isTvAlert && (
                              <span className="px-1.5 py-0.5 rounded bg-fuchsia-500/15 text-fuchsia-300 border border-fuchsia-500/30">
                                TV
                              </span>
                            )}
                            {row.scan_source}
                          </span>
                        </div>
                        <div className="text-[11px] edith-subtitle mt-1 truncate">{row.pattern || row.label}</div>
                        <div className="flex flex-wrap gap-2 mt-1.5 text-[10px]">
                          <span className="text-emerald-400">{fmtPct(conf)} conf</span>
                          {row.symbol_math_score != null && (
                            <span className="text-sky-400">math {row.symbol_math_score}</span>
                          )}
                          {isTvAlert && row.trade_status && (
                            <span className="text-fuchsia-300">{row.trade_status}</span>
                          )}
                          {row.entry_allowed ? (
                            <span className="text-emerald-400">entry ok</span>
                          ) : (
                            <span className="text-amber-400">hold</span>
                          )}
                          {!row.chart_ready && <span className="text-rose-400">no chart</span>}
                        </div>
                        {isTvAlert && tvChartUrl && (
                          <a
                            href={tvChartUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 mt-2 text-[10px] text-cyan-400 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Open in TV
                            <ExternalLink size={10} />
                          </a>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <div className="space-y-4">
            <section className="edith-panel edith-scan-wrap p-4">
              <div className="jarvis-scan-line" aria-hidden />
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-sm font-semibold edith-value flex items-center gap-2">
                    {selected?.symbol || '—'}
                    {selected?.pattern && (
                      <span className="text-xs edith-subtitle font-normal">· {selected.pattern}</span>
                    )}
                  </h2>
                  <p className="text-xs edith-subtitle mt-1 max-w-2xl">
                    {selected?.label || (setup?.label ? String(setup.label) : '—')}
                  </p>
                </div>
                {trend && chartMode === 'jarvis' && (
                  <div className="flex items-center gap-2 text-xs">
                    <TrendingUp size={14} className="text-cyan-400" />
                    <span className="edith-value capitalize">{trend.label}</span>
                    <span className="edith-subtitle">
                      bull {((trend.bull_score ?? 0) * 100).toFixed(0)}% · bear{' '}
                      {((trend.bear_score ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-1">
                  {(
                    [
                      ['jarvis', 'Jarvis'],
                      ['tradingview', 'TradingView'],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      className={`text-[10px] px-2 py-0.5 rounded border ${
                        chartMode === id
                          ? 'border-cyan-500/50 text-cyan-300'
                          : 'border-white/10 edith-subtitle'
                      }`}
                      onClick={() => setChartMode(id)}
                    >
                      {label}
                    </button>
                  ))}
                  {selected?.chart_url && (
                    <a
                      href={selected.chart_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="edith-btn edith-btn-sm edith-btn-ghost ml-1"
                    >
                      <ExternalLink size={12} />
                      Open in TV
                    </a>
                  )}
                </div>
              </div>

              {chartMode === 'tradingview' && selected?.tradingview_symbol ? (
                <TradingViewChart
                  key={`tv-${selected.tradingview_symbol}-${tvLink?.interval ?? '5'}`}
                  symbol={selected.tradingview_symbol}
                  interval={tvLink?.interval ?? '5'}
                  theme={(tvLink?.theme as 'light' | 'dark') ?? 'dark'}
                  height={420}
                />
              ) : chartLoading ? (
                <div className="flex items-center justify-center h-[420px] edith-subtitle text-sm">Loading chart…</div>
              ) : (
                <SetupCandleChart
                  key={`${selected?.symbol}-${selected?.pattern}-${chart?.updated_at ?? 0}`}
                  data={chart}
                  height={420}
                />
              )}

              {chartMode === 'jarvis' && (
              <div className="flex flex-wrap gap-2 mt-3 text-[10px]">
                <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">Candles</span>
                <span className="px-2 py-0.5 rounded bg-sky-500/15 text-sky-400">EMA 9/21</span>
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300">Support</span>
                <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-300">Resistance</span>
                <span className="px-2 py-0.5 rounded bg-violet-500/15 text-violet-300">FVG zone</span>
                <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300">Fib</span>
                <span className="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300">Setup arrow</span>
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300">Open / win</span>
                <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-300">Loss / stop</span>
              </div>
              )}
            </section>

            {selected && (
              <section className="edith-panel p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <h3 className="edith-label uppercase tracking-wider mb-2">Pattern tools</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {((selected.tools?.length ? selected.tools : (setup?.tools as string[] | undefined)) || []).map((t) => (
                      <span key={t} className="px-2 py-0.5 rounded bg-white/5 edith-subtitle">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="edith-label uppercase tracking-wider mb-2">Confirmation</h3>
                  <ul className="edith-subtitle space-y-1">
                    {(selected.confirmation_pass || (setup?.confirmation_pass as string[]) || []).slice(0, 4).map((line) => (
                      <li key={line} className="text-emerald-400/90">
                        ✓ {line}
                      </li>
                    ))}
                    {(selected.confirmation_fail || (setup?.confirmation_fail as string[]) || []).slice(0, 3).map((line) => (
                      <li key={line} className="text-amber-400/90">
                        ✗ {line}
                      </li>
                    ))}
                  </ul>
                </div>
                {selected.symbol_math && (
                  <div className="md:col-span-2 border-t border-white/10 pt-3">
                    <h3 className="edith-label uppercase tracking-wider mb-2">Symbol math</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 edith-subtitle">
                      <div>
                        Style: <span className="edith-value">{String(selected.symbol_math.style || '—')}</span>
                      </div>
                      <div>
                        Swing:{' '}
                        <span className="edith-value">
                          {selected.symbol_math.swing_pct != null
                            ? `${(Number(selected.symbol_math.swing_pct) * 100).toFixed(1)}%`
                            : '—'}
                        </span>
                      </div>
                      <div>
                        Min profit:{' '}
                        <span className="text-emerald-400">
                          {selected.symbol_math.min_profit_pct != null
                            ? `${(Number(selected.symbol_math.min_profit_pct) * 100).toFixed(1)}%`
                            : '—'}
                        </span>
                      </div>
                      <div>
                        Target:{' '}
                        <span className="text-emerald-400">
                          {selected.symbol_math.target_move_pct != null
                            ? `${(Number(selected.symbol_math.target_move_pct) * 100).toFixed(1)}%`
                            : '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
