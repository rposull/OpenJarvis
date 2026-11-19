import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { ExternalLink, LineChart, RefreshCw, TrendingUp } from 'lucide-react';
import {
  fetchFreqtradeStatus,
  startFreqtradeBot,
  stopFreqtradeBot,
  type FreqtradeStatus,
  type FreqtradeTrade,
} from '../lib/api';
import '../styles/trading-edith.css';

function fmtUsd(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}$${Math.abs(n).toFixed(2)}`;
}

function fmtRatioPct(ratio: number | undefined | null, signed = false): string {
  if (ratio == null || Number.isNaN(ratio)) return '—';
  const pct = ratio * 100;
  const prefix = signed && pct > 0 ? '+' : '';
  return `${prefix}${pct.toFixed(2)}%`;
}

export function FreqtradePage() {
  const [freqtrade, setFreqtrade] = useState<FreqtradeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchFreqtradeStatus();
      setFreqtrade(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Freqtrade status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 8000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const ftProfit = freqtrade?.profit;
  const ftOpenTrades = freqtrade?.open_trades_list ?? [];
  const ftClosedTrades = freqtrade?.closed_trades ?? [];
  const nautLearner = freqtrade?.nautilus?.learner;
  const nautValidations = freqtrade?.nautilus_validations ?? {};
  const whitelistPairs = Object.keys(nautValidations).filter((p) => p.includes('/'));
  const showConfig = freqtrade?.show_config as Record<string, unknown> | undefined;
  const exchange =
    typeof showConfig?.exchange === 'string'
      ? showConfig.exchange
      : (showConfig?.exchange as { name?: string } | undefined)?.name;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10 edith-trading">
      <div className="cosmos-layer cosmos-nebula" aria-hidden />
      <div className="cosmos-layer cosmos-aurora" aria-hidden />
      <div className="cosmos-layer cosmos-stars" aria-hidden />

      <div className="relative z-10 max-w-6xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-xl font-semibold edith-value tracking-wide flex items-center gap-2">
              <LineChart size={22} style={{ color: 'var(--edith-cyan)' }} />
              Freqtrade
            </h1>
            <p className="text-sm edith-subtitle mt-1">
              Spot bot (dry-run) — separate from the Jarvis option paper stack
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/trading" className="edith-btn edith-btn-sm edith-btn-ghost">
              Options Trading
            </Link>
            <Link to="/nautilus" className="edith-btn edith-btn-sm edith-btn-ghost">
              Nautilus
            </Link>
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              onClick={() => refresh()}
              disabled={loading}
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="edith-panel mb-4 p-3 text-sm text-rose-400 border border-rose-500/30">
            {error}
          </div>
        )}

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <div className="jarvis-scan-line" aria-hidden />
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2">
              <TrendingUp size={16} style={{ color: 'var(--edith-cyan)' }} />
              Bot Control
            </h2>
            <span className="text-xs edith-subtitle">
              {freqtrade?.supervisor_running ? 'RUNNING' : 'STOPPED'}
              {freqtrade?.dry_run !== false ? ' · dry-run' : ' · LIVE'}
              {freqtrade?.api_reachable ? ` · ${freqtrade.state || 'online'}` : ' · API offline'}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
            {[
              { label: 'Equity', value: fmtUsd(freqtrade?.balance?.total), hero: true },
              { label: 'Strategy', value: freqtrade?.strategy || '—' },
              { label: 'Exchange', value: exchange || '—' },
              { label: 'Open', value: `${freqtrade?.open_trades ?? 0}${freqtrade?.max_open_trades != null ? ` / ${freqtrade.max_open_trades}` : ''}` },
              { label: 'PID', value: freqtrade?.supervisor_pid ? String(freqtrade.supervisor_pid) : '—' },
              { label: 'API', value: freqtrade?.api_url?.replace('http://', '') || '—' },
            ].map((item) => (
              <div key={item.label} className={`edith-stat px-3 py-2 ${item.hero ? 'edith-stat-hero' : ''}`}>
                <div className="edith-label">{item.label}</div>
                <div className="edith-value text-sm font-medium mt-1 truncate" title={item.value}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>

          {nautLearner && (
            <p className="text-xs edith-subtitle mb-3">
              Nautilus gate: min WR{' '}
              {Math.round(Number(nautLearner.effective_min_win_rate ?? 0.42) * 100)}%
              {nautLearner.passed_samples ? (
                <> · live passed-trade WR {String(nautLearner.passed_win_rate_pct)}%</>
              ) : null}
              {' '}· entries blocked when backtest FAIL
            </p>
          )}

          {whitelistPairs.length > 0 && (
            <div className="mb-4">
              <div className="text-xs edith-label mb-2 uppercase tracking-wider">
                Whitelist Nautilus ({whitelistPairs.length} pairs)
              </div>
              <div className="flex flex-wrap gap-2">
                {whitelistPairs.map((pair) => {
                  const nb = nautValidations[pair];
                  const pass = nb?.passed === true;
                  const fail = nb && nb.passed === false;
                  return (
                    <span
                      key={pair}
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                        pass ? 'text-emerald-400 bg-emerald-500/10' : fail ? 'text-rose-400 bg-rose-500/10' : 'edith-subtitle bg-white/5'
                      }`}
                      title={nb?.gate_reason || nb?.error || undefined}
                    >
                      {pair} {pass ? 'PASS' : fail ? 'FAIL' : '—'}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 text-xs edith-subtitle">
            <button
              type="button"
              className="edith-btn edith-btn-sm"
              disabled={busy || !!freqtrade?.supervisor_running}
              onClick={async () => {
                setBusy(true);
                try {
                  await startFreqtradeBot();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Start failed');
                } finally {
                  setBusy(false);
                }
              }}
            >
              Start
            </button>
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              disabled={busy || !freqtrade?.supervisor_running}
              onClick={async () => {
                setBusy(true);
                try {
                  await stopFreqtradeBot();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Stop failed');
                } finally {
                  setBusy(false);
                }
              }}
            >
              Stop
            </button>
            <a
              href="http://127.0.0.1:8080/docs"
              target="_blank"
              rel="noreferrer"
              className="edith-link inline-flex items-center gap-1"
            >
              Swagger API <ExternalLink size={12} />
            </a>
            <span className="opacity-70">
              Config: {freqtrade?.config_path || '~/.openjarvis/freqtrade/user_data/config.json'}
            </span>
          </div>
        </section>

        {freqtrade?.balance?.currencies && freqtrade.balance.currencies.length > 0 && (
          <section className="edith-panel edith-scan-wrap mb-6 p-4">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3">
              Wallet
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs edith-subtitle">
                <thead>
                  <tr className="text-left border-b border-white/10">
                    <th className="py-1 pr-3">Currency</th>
                    <th className="py-1 pr-3">Free</th>
                    <th className="py-1 pr-3">Balance</th>
                    <th className="py-1 pr-3">Used</th>
                    <th className="py-1">Est. Stake</th>
                  </tr>
                </thead>
                <tbody>
                  {freqtrade.balance.currencies.map((c) => (
                    <tr key={c.currency} className="border-b border-white/5">
                      <td className="py-1.5 pr-3 edith-value">{c.currency}</td>
                      <td className="py-1.5 pr-3">{c.free?.toFixed(4) ?? '—'}</td>
                      <td className="py-1.5 pr-3">{c.balance?.toFixed(4) ?? '—'}</td>
                      <td className="py-1.5 pr-3">{c.used?.toFixed(4) ?? '—'}</td>
                      <td className="py-1.5">{c.est_stake != null ? fmtUsd(c.est_stake) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className="edith-panel edith-scan-wrap mb-6 p-4">
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase mb-3">
            Performance
          </h2>

          {freqtrade?.api_reachable ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-4">
                {[
                  { label: 'Closed PnL', value: fmtUsd(ftProfit?.profit_closed_fiat, true), hero: true },
                  { label: 'All PnL', value: fmtUsd(ftProfit?.profit_all_fiat, true), hero: true },
                  { label: 'Win Rate', value: `${((ftProfit?.winrate ?? 0) * 100).toFixed(1)}%` },
                  { label: 'Closed', value: String(ftProfit?.closed_trade_count ?? 0) },
                  { label: 'W / L', value: `${ftProfit?.winning_trades ?? 0} / ${ftProfit?.losing_trades ?? 0}` },
                  { label: 'Profit Factor', value: ftProfit?.profit_factor != null ? String(ftProfit.profit_factor) : '—' },
                  { label: 'Best Pair', value: ftProfit?.best_pair || '—' },
                  { label: 'Started', value: ftProfit?.bot_start_date?.split(' ')[0] || '—' },
                ].map((item) => (
                  <div
                    key={item.label}
                    className={`edith-stat px-3 py-2 ${item.hero ? 'edith-stat-hero' : ''}`}
                  >
                    <div className="edith-label">{item.label}</div>
                    <div className="edith-value text-sm font-medium mt-1 truncate" title={item.value}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>

              {ftOpenTrades.length > 0 ? (
                <div className="mb-4">
                  <div className="text-xs edith-label mb-2 uppercase tracking-wider">Open Trades</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs edith-subtitle">
                      <thead>
                        <tr className="text-left border-b border-white/10">
                          <th className="py-1 pr-3">Pair</th>
                          <th className="py-1 pr-3">Nautilus</th>
                          <th className="py-1 pr-3">Entry</th>
                          <th className="py-1 pr-3">Current</th>
                          <th className="py-1 pr-3">Stake</th>
                          <th className="py-1 pr-3">uPnL</th>
                          <th className="py-1">Opened</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ftOpenTrades.map((t: FreqtradeTrade) => {
                          const nb = t.nautilus_backtest;
                          const nbPass = nb?.passed === true;
                          const nbFail = nb && nb.passed === false;
                          return (
                          <tr key={t.trade_id ?? t.pair} className="border-b border-white/5">
                            <td className="py-1.5 pr-3 edith-value">{t.pair}</td>
                            <td className={`py-1.5 pr-3 text-[10px] font-semibold ${nbPass ? 'text-emerald-400' : nbFail ? 'text-rose-400' : 'edith-subtitle'}`}>
                              {nb ? (nbPass ? 'PASS' : nbFail ? 'FAIL' : '—') : '—'}
                            </td>
                            <td className="py-1.5 pr-3">{t.open_rate?.toFixed(4) ?? '—'}</td>
                            <td className="py-1.5 pr-3">{t.current_rate?.toFixed(4) ?? '—'}</td>
                            <td className="py-1.5 pr-3">{fmtUsd(t.stake_amount)}</td>
                            <td className={`py-1.5 pr-3 ${(t.profit_ratio ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {fmtRatioPct(t.profit_ratio, true)}
                            </td>
                            <td className="py-1.5">{t.open_date?.replace('T', ' ').slice(0, 16) ?? '—'}</td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="text-xs edith-subtitle mb-4">No open positions.</div>
              )}

              {ftClosedTrades.length > 0 ? (
                <div>
                  <div className="text-xs edith-label mb-2 uppercase tracking-wider">
                    Recent Closed ({freqtrade.closed_trades_total ?? ftClosedTrades.length})
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs edith-subtitle">
                      <thead>
                        <tr className="text-left border-b border-white/10">
                          <th className="py-1 pr-3">Pair</th>
                          <th className="py-1 pr-3">Entry</th>
                          <th className="py-1 pr-3">Exit</th>
                          <th className="py-1 pr-3">PnL</th>
                          <th className="py-1 pr-3">Reason</th>
                          <th className="py-1">Closed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ftClosedTrades.map((t: FreqtradeTrade) => (
                          <tr key={t.trade_id ?? `${t.pair}-${t.close_date}`} className="border-b border-white/5">
                            <td className="py-1.5 pr-3 edith-value">{t.pair}</td>
                            <td className="py-1.5 pr-3">{t.open_rate?.toFixed(4) ?? '—'}</td>
                            <td className="py-1.5 pr-3">{t.close_rate?.toFixed(4) ?? '—'}</td>
                            <td className={`py-1.5 pr-3 ${(t.profit_ratio ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {fmtRatioPct(t.profit_ratio, true)}
                              {t.profit_abs != null ? ` (${fmtUsd(t.profit_abs, true)})` : ''}
                            </td>
                            <td className="py-1.5 pr-3">{t.exit_reason || '—'}</td>
                            <td className="py-1.5">{t.close_date?.replace('T', ' ').slice(0, 16) ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="text-xs edith-subtitle">No closed trades yet.</div>
              )}
            </>
          ) : (
            <div className="text-xs edith-subtitle">
              Start the bot with the button above, or run{' '}
              <code className="opacity-80">scripts/start-freqtrade.ps1</code>.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
