import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Activity, AlertTriangle, Database, LineChart, RefreshCw, Shield, TrendingUp } from 'lucide-react';
import {
  fetchNautilusHistory,
  fetchNautilusStatus,
  fetchNautilusStrategies,
  runNautilusBacktest,
  startNautilusWorker,
  stopNautilusWorker,
  type NautilusBacktestResult,
  type NautilusStatus,
  type NautilusStrategy,
} from '../lib/api';
import '../styles/trading-edith.css';

function fmtUsd(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}$${Math.abs(n).toFixed(2)}`;
}

function fmtPct(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];

export function NautilusPage() {
  const [nautilus, setNautilus] = useState<NautilusStatus | null>(null);
  const [strategies, setStrategies] = useState<NautilusStrategy[]>([]);
  const [history, setHistory] = useState<Record<string, unknown> | null>(null);
  const [backtestResult, setBacktestResult] = useState<NautilusBacktestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [symbol, setSymbol] = useState('BTC-USD');
  const [timeframe, setTimeframe] = useState('1h');
  const [strategy, setStrategy] = useState('ma_crossover');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [status, strat, hist] = await Promise.all([
        fetchNautilusStatus(),
        fetchNautilusStrategies(),
        fetchNautilusHistory(10),
      ]);
      setNautilus(status);
      setStrategies(strat.strategies ?? []);
      setHistory(hist);
      if (status.default_strategy) setStrategy(status.default_strategy);
      if (status.default_timeframe) setTimeframe(status.default_timeframe);
      if (status.symbols?.[0]) setSymbol(status.symbols[0]);
      if (status.last_backtest && !backtestResult) {
        setBacktestResult(status.last_backtest as NautilusBacktestResult);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Nautilus status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 12000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const lastBt = backtestResult ?? (nautilus?.last_backtest as NautilusBacktestResult | undefined);
  const dataConn = nautilus?.data_connection as Record<string, unknown> | undefined;
  const metrics = nautilus?.metrics as Record<string, unknown> | undefined;
  const paperPositions = (history?.paper_positions as Array<Record<string, unknown>>) ?? [];
  const recentErrors = (history?.errors as Array<Record<string, unknown>>) ?? [];
  const recentBacktests = (history?.backtests as Array<Record<string, unknown>>) ?? [];

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10 edith-trading">
      <div className="cosmos-layer cosmos-nebula" aria-hidden />
      <div className="cosmos-layer cosmos-aurora" aria-hidden />
      <div className="cosmos-layer cosmos-stars" aria-hidden />

      <div className="relative z-10 max-w-6xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-xl font-semibold edith-value tracking-wide flex items-center gap-2">
              <Activity size={22} style={{ color: 'var(--edith-cyan)' }} />
              Nautilus Trader Engine
            </h1>
            <p className="text-sm edith-subtitle mt-1">
              Backtest &amp; paper trading — live mode locked until you edit trading.toml
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/trading" className="edith-btn edith-btn-sm edith-btn-ghost">Options</Link>
            <Link to="/freqtrade" className="edith-btn edith-btn-sm edith-btn-ghost">Freqtrade</Link>
            <button type="button" className="edith-btn edith-btn-sm edith-btn-ghost" onClick={() => refresh()} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="edith-panel mb-4 p-3 text-sm text-rose-400 border border-rose-500/30">{error}</div>
        )}

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <div className="jarvis-scan-line" aria-hidden />
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3 flex items-center gap-2">
            <Shield size={16} style={{ color: 'var(--edith-cyan)' }} /> Engine Status
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {[
              { label: 'Mode', value: (nautilus?.mode || '—').toUpperCase(), hero: true },
              { label: 'Worker', value: nautilus?.supervisor_running ? 'RUNNING' : 'STOPPED' },
              { label: 'Version', value: nautilus?.version || '—' },
              { label: 'Data', value: dataConn?.ok ? `OK (${dataConn.source})` : 'OFFLINE' },
              { label: 'Live lock', value: nautilus?.live_trading_unlock ? 'UNLOCKED' : 'LOCKED' },
              { label: 'Paper only', value: nautilus?.paper_only ? 'YES' : 'NO' },
            ].map((item) => (
              <div key={item.label} className={`edith-stat px-3 py-2 ${item.hero ? 'edith-stat-hero' : ''}`}>
                <div className="edith-label">{item.label}</div>
                <div className="edith-value text-sm font-medium mt-1 truncate">{item.value}</div>
              </div>
            ))}
          </div>
          {!nautilus?.live_trading_unlock && (
            <p className="text-xs edith-subtitle mt-3 flex items-center gap-1">
              <AlertTriangle size={12} /> Live trading blocked. Set <code>live_trading_unlock = true</code> in <code>[nautilus]</code> manually.
            </p>
          )}
          <div className="flex gap-2 mt-3">
            <button type="button" className="edith-btn edith-btn-sm" disabled={busy || !!nautilus?.supervisor_running}
              onClick={async () => { setBusy(true); try { await startNautilusWorker(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Start failed'); } finally { setBusy(false); } }}>
              Start worker
            </button>
            <button type="button" className="edith-btn edith-btn-sm edith-btn-ghost" disabled={busy || !nautilus?.supervisor_running}
              onClick={async () => { setBusy(true); try { await stopNautilusWorker(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Stop failed'); } finally { setBusy(false); } }}>
              Stop worker
            </button>
          </div>
        </section>

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3 flex items-center gap-2">
            <Database size={16} style={{ color: 'var(--edith-cyan)' }} /> Data Connection
          </h2>
          {dataConn?.ok ? (
            <p className="text-sm edith-subtitle">
              {String(dataConn.symbol)} · {String(dataConn.timeframe)} · source {String(dataConn.source)} · {String(dataConn.bars)} bars
              {dataConn.start ? ` · ${String(dataConn.start)} → ${String(dataConn.end)}` : ''}
            </p>
          ) : (
            <p className="text-sm text-amber-400">
              {String(dataConn?.error || nautilus?.last_error || 'No data connection. Check network or set ccxt_api_key in trading.toml.')}
              {dataConn?.needs_api_key ? ' API key required for this source.' : ''}
            </p>
          )}
        </section>

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3 flex items-center gap-2">
            <LineChart size={16} style={{ color: 'var(--edith-cyan)' }} /> Run Backtest
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-3 text-xs">
            <label className="flex flex-col gap-1">
              <span className="edith-label">Symbol</span>
              <select className="edith-input" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {(nautilus?.symbols ?? ['BTC-USD', 'ETH-USD', 'SOL-USD']).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="edith-label">Timeframe</span>
              <select className="edith-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 col-span-2">
              <span className="edith-label">Strategy</span>
              <select className="edith-input" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                {strategies.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="edith-label">Start date</span>
              <input type="date" className="edith-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="edith-label">End date</span>
              <input type="date" className="edith-input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </label>
          </div>
          <button type="button" className="edith-btn edith-btn-sm" disabled={busy}
            onClick={async () => {
              setBusy(true); setError('');
              try {
                const result = await runNautilusBacktest({
                  symbol, timeframe, strategy,
                  start_date: startDate || undefined,
                  end_date: endDate || undefined,
                  mode: 'backtest',
                });
                setBacktestResult(result);
                await refresh();
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Backtest failed');
              } finally { setBusy(false); }
            }}>
            Run backtest
          </button>
        </section>

        {lastBt && (
          <section className="edith-panel edith-scan-wrap mb-6 p-4">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3 flex items-center gap-2">
              <TrendingUp size={16} style={{ color: 'var(--edith-cyan)' }} /> Last Backtest Results
            </h2>
            {!lastBt.ok ? (
              <p className="text-sm text-rose-400">{lastBt.error || 'Backtest failed'}</p>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                  {[
                    { label: 'PnL', value: fmtUsd(lastBt.total_pnl, true), hero: true },
                    { label: 'Win rate', value: fmtPct(lastBt.win_rate) },
                    { label: 'Max DD', value: fmtPct(lastBt.max_drawdown) },
                    { label: 'Trades', value: String(lastBt.trades ?? '—') },
                    { label: 'Bars', value: String(lastBt.bars ?? '—') },
                  ].map((item) => (
                    <div key={item.label} className={`edith-stat px-3 py-2 ${item.hero ? 'edith-stat-hero' : ''}`}>
                      <div className="edith-label">{item.label}</div>
                      <div className="edith-value text-sm font-medium mt-1">{item.value}</div>
                    </div>
                  ))}
                </div>
                {(lastBt.trade_log?.length ?? 0) > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs edith-subtitle">
                      <thead>
                        <tr className="text-left border-b border-white/10">
                          <th className="py-1 pr-3">Side</th>
                          <th className="py-1 pr-3">Entry</th>
                          <th className="py-1 pr-3">Exit</th>
                          <th className="py-1 pr-3">PnL</th>
                          <th className="py-1 pr-3">Entry reason</th>
                          <th className="py-1">Exit reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(lastBt.trade_log ?? []).slice(-15).map((t, i) => (
                          <tr key={i} className="border-b border-white/5">
                            <td className="py-1 pr-3">{String(t.side)}</td>
                            <td className="py-1 pr-3">{Number(t.entry_price).toFixed(2)}</td>
                            <td className="py-1 pr-3">{Number(t.exit_price).toFixed(2)}</td>
                            <td className="py-1 pr-3">{fmtUsd(Number(t.pnl), true)}</td>
                            <td className="py-1 pr-3">{String(t.entry_reason)}</td>
                            <td className="py-1">{String(t.exit_reason)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-1">Research totals</h2>
          <p className="text-xs edith-subtitle mb-3 opacity-80">
            Historical replays stored in SQLite — not your live or paper account balance. Use Last backtest
            and Backtest history for one-run results.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm edith-subtitle">
            <div title="Count of backtest runs logged, not live trade count">
              Backtest runs: {String(metrics?.backtests ?? 0)}
            </div>
            <div>Avg win rate: {fmtPct(Number(metrics?.avg_win_rate))}</div>
            <div title="Sum of PnL from every replay — overlapping periods counted many times">
              Sum PnL (all replays): {fmtUsd(Number(metrics?.sum_pnl), true)}
            </div>
            <div>Worst DD: {fmtPct(Number(metrics?.worst_drawdown))}</div>
          </div>
          {metrics?.trade_rows != null && (
            <div className="text-xs edith-subtitle mt-2 opacity-70">
              Simulated trade rows across all replays: {String(metrics.trade_rows)}
            </div>
          )}
        </section>

        {paperPositions.length > 0 && (
          <section className="edith-panel edith-scan-wrap mb-6 p-4">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-2">Paper Positions</h2>
            <pre className="text-xs edith-subtitle overflow-x-auto">{JSON.stringify(paperPositions, null, 2)}</pre>
          </section>
        )}

        {recentBacktests.length > 0 && (
          <section className="edith-panel edith-scan-wrap mb-6 p-4">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-2">Backtest History</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs edith-subtitle">
                <thead>
                  <tr className="text-left border-b border-white/10">
                    <th className="py-1 pr-3">ID</th>
                    <th className="py-1 pr-3">Symbol</th>
                    <th className="py-1 pr-3">Strategy</th>
                    <th className="py-1 pr-3">PnL</th>
                    <th className="py-1 pr-3">Win%</th>
                    <th className="py-1">Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {recentBacktests.map((row) => (
                    <tr key={String(row.id)} className="border-b border-white/5">
                      <td className="py-1 pr-3">{String(row.id)}</td>
                      <td className="py-1 pr-3">{String(row.symbol)}</td>
                      <td className="py-1 pr-3">{String(row.strategy)}</td>
                      <td className="py-1 pr-3">{fmtUsd(Number(row.total_pnl), true)}</td>
                      <td className="py-1 pr-3">{fmtPct(Number(row.win_rate))}</td>
                      <td className="py-1">{String(row.trades)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {(nautilus?.last_error || recentErrors.length > 0) && (
          <section className="edith-panel edith-scan-wrap mb-6 p-4 border border-amber-500/20">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-2">Logs / Errors</h2>
            {nautilus?.last_error && <pre className="text-xs edith-subtitle whitespace-pre-wrap mb-2">{nautilus.last_error}</pre>}
            {recentErrors.slice(0, 5).map((e) => (
              <div key={String(e.id)} className="text-xs edith-subtitle mb-1">
                [{String(e.component)}] {String(e.message)}
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
