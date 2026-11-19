import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  Briefcase,
  Brain,
  RefreshCw,
  Shield,
  TrendingDown,
  TrendingUp,
  Waves,
} from 'lucide-react';
import { fetchHedgeFundDesk, runHedgeFundCheckSetups, runHedgeFundExecute, runHedgeFundLearnSymbols, runHedgeFundSweep, type HedgeFundDesk } from '../lib/api';
import '../styles/trading-edith.css';

function fmtUsd(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}$${Math.abs(n).toFixed(2)}`;
}

function fmtPct(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}${n.toFixed(1)}%`;
}

function regimeColor(regime?: string): string {
  switch (regime) {
    case 'risk_on':
      return 'text-emerald-400';
    case 'risk_off':
      return 'text-rose-400';
    case 'high_vol':
      return 'text-amber-400';
    case 'low_vol':
      return 'text-sky-400';
    default:
      return 'var(--edith-cyan)';
  }
}

export function HedgeFundPage() {
  const [desk, setDesk] = useState<HedgeFundDesk | null>(null);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchHedgeFundDesk();
      setDesk(data);
      if (data.error && !data.ok) setError(data.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load desk');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 15000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const regime = desk?.regime;
  const portfolio = desk?.portfolio;
  const allocation = desk?.allocation;
  const edges = desk?.learned_edges;
  const best = edges?.structure?.best_structures ?? [];
  const worst = edges?.structure?.worst_structures ?? [];
  const topPatterns = edges?.patterns?.top ?? [];
  const genius = desk?.market_genius;
  const playbook = desk?.playbook;
  const geniusWorks = genius?.works ?? [];
  const geniusFails = genius?.fails ?? [];
  const symbolProfiles = desk?.symbol_math?.profiles ?? [];

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10 edith-trading">
      <div className="cosmos-layer cosmos-nebula" aria-hidden />
      <div className="cosmos-layer cosmos-aurora" aria-hidden />
      <div className="cosmos-layer cosmos-stars" aria-hidden />

      <div className="relative z-10 max-w-6xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-xl font-semibold edith-value tracking-wide flex items-center gap-2">
              <Briefcase size={22} style={{ color: 'var(--edith-cyan)' }} />
              Hedge Fund Desk
            </h1>
            <p className="text-sm edith-subtitle mt-1 max-w-xl">
              {desk?.philosophy ??
                'Observe regimes, learn what works, adapt risk — we do not forecast prices.'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/trading" className="edith-btn edith-btn-sm edith-btn-ghost">
              Trading
            </Link>
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              disabled={sweeping || loading}
              onClick={async () => {
                setSweeping(true);
                setError('');
                try {
                  await runHedgeFundExecute();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Execute playbook failed');
                } finally {
                  setSweeping(false);
                }
              }}
            >
              Execute Plan
            </button>
            <button
              type="button"
              className="edith-btn edith-btn-sm"
              disabled={sweeping || loading}
              onClick={async () => {
                setSweeping(true);
                setError('');
                try {
                  await runHedgeFundSweep(true);
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Genius sweep failed');
                } finally {
                  setSweeping(false);
                }
              }}
            >
              {sweeping ? 'Sweeping…' : 'Run Genius Sweep'}
            </button>
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              disabled={sweeping || loading}
              onClick={async () => {
                setSweeping(true);
                setError('');
                try {
                  await runHedgeFundLearnSymbols();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Learn symbols failed');
                } finally {
                  setSweeping(false);
                }
              }}
            >
              Learn Symbols
            </button>
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              disabled={sweeping || loading}
              onClick={async () => {
                setSweeping(true);
                setError('');
                try {
                  await runHedgeFundCheckSetups();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Check setups failed');
                } finally {
                  setSweeping(false);
                }
              }}
            >
              Check Setups
            </button>
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

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <section className="edith-panel edith-scan-wrap p-4">
            <div className="jarvis-scan-line" aria-hidden />
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2 mb-3">
              <Waves size={16} style={{ color: 'var(--edith-cyan)' }} />
              Market Regime (observe)
            </h2>
            <div className="flex flex-wrap items-baseline gap-2 mb-2">
              <span
                className={`text-2xl font-semibold uppercase ${regimeColor(regime?.regime)}`}
              >
                {regime?.regime?.replace(/_/g, ' ') ?? '—'}
              </span>
              <span className="text-xs edith-subtitle">
                stance: {regime?.stance?.replace(/_/g, ' ') ?? '—'}
              </span>
            </div>
            <p className="text-sm edith-subtitle mb-3">
              {regime?.desk_note ?? regime?.observation ?? 'Loading BTC trend + vol observation…'}
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'BTC trend', value: regime?.btc_trend_score?.toFixed(2) ?? '—' },
                { label: 'Vol regime', value: regime?.vol_regime_score?.toFixed(2) ?? '—' },
                { label: 'Hybrid', value: regime?.hybrid_score?.toFixed(2) ?? '—' },
              ].map((item) => (
                <div key={item.label} className="edith-stat px-2 py-2">
                  <div className="edith-label text-[10px]">{item.label}</div>
                  <div className="edith-value text-sm mt-1">{item.value}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="edith-panel edith-scan-wrap p-4">
            <div className="jarvis-scan-line" aria-hidden />
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2 mb-3">
              <Shield size={16} style={{ color: 'var(--edith-cyan)' }} />
              Risk Posture (adapt)
            </h2>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="edith-stat edith-stat-hero px-3 py-2">
                <div className="edith-label">Deploy cap</div>
                <div className="edith-value text-lg font-medium mt-1">
                  {allocation?.recommended_deploy_pct != null
                    ? `${allocation.recommended_deploy_pct}%`
                    : '—'}
                </div>
              </div>
              <div className="edith-stat px-3 py-2">
                <div className="edith-label">Max concurrent</div>
                <div className="edith-value text-lg font-medium mt-1">
                  {allocation?.max_concurrent_bets ?? '—'}
                </div>
              </div>
            </div>
            <ul className="text-xs edith-subtitle space-y-1 mb-3">
              {(allocation?.rationale ?? []).map((line) => (
                <li key={line}>· {line}</li>
              ))}
            </ul>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {[
                { label: 'Equity', value: fmtUsd(portfolio?.equity) },
                { label: 'Return', value: fmtPct(portfolio?.return_pct, true) },
                { label: 'Book WR', value: fmtPct(portfolio?.win_rate_pct) },
                { label: 'Open', value: String(portfolio?.open_positions ?? 0) },
              ].map((item) => (
                <div key={item.label} className="edith-stat px-2 py-2">
                  <div className="edith-label text-[10px]">{item.label}</div>
                  <div className="edith-value text-sm mt-1">{item.value}</div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="edith-panel edith-scan-wrap p-4 mb-6">
          <div className="jarvis-scan-line" aria-hidden />
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2 mb-3">
            <Brain size={16} style={{ color: 'var(--edith-cyan)' }} />
            Learned Edges
            <span className="text-[10px] edith-subtitle font-normal normal-case tracking-normal">
              · {edges?.structure?.trades_recorded ?? 0} trades recorded · rolling WR{' '}
              {edges?.win_rate_optimizer?.rolling_win_rate_pct ?? '—'}%
            </span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs edith-label mb-2 uppercase tracking-wider flex items-center gap-1">
                <TrendingUp size={12} className="text-emerald-400" />
                Structures that paid
              </div>
              {best.length > 0 ? (
                <ul className="space-y-1.5 max-h-48 overflow-y-auto">
                  {best.map((row) => (
                    <li
                      key={String(row.pattern) + String(row.symbol)}
                      className="text-xs flex justify-between gap-2 edith-subtitle border-b border-white/5 pb-1"
                    >
                      <span className="edith-value truncate">
                        {String(row.pattern)} · {String(row.symbol || '*')} ·{' '}
                        {String(row.direction || '*')}
                      </span>
                      <span className="text-emerald-400 shrink-0">
                        {Math.round(Number(row.win_rate ?? 0) * 100)}% ({String(row.samples ?? 0)}n)
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs edith-subtitle">No proven structures yet — desk learns from closes.</p>
              )}
            </div>

            <div>
              <div className="text-xs edith-label mb-2 uppercase tracking-wider flex items-center gap-1">
                <TrendingDown size={12} className="text-rose-400" />
                Structures to avoid
              </div>
              {worst.length > 0 ? (
                <ul className="space-y-1.5 max-h-48 overflow-y-auto">
                  {worst.map((row) => (
                    <li
                      key={String(row.pattern) + String(row.symbol) + 'w'}
                      className="text-xs flex justify-between gap-2 edith-subtitle border-b border-white/5 pb-1"
                    >
                      <span className="edith-value truncate">
                        {String(row.pattern)} · {String(row.symbol || '*')}
                      </span>
                      <span className="text-rose-400 shrink-0">
                        {Math.round(Number(row.win_rate ?? 0) * 100)}% ({String(row.samples ?? 0)}n)
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs edith-subtitle">No rejected structures yet.</p>
              )}
            </div>
          </div>

          {topPatterns.length > 0 && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <div className="text-xs edith-label mb-2 uppercase tracking-wider">Top patterns (book)</div>
              <div className="flex flex-wrap gap-2">
                {topPatterns.map((p) => (
                  <span
                    key={String(p.pattern)}
                    className="text-[10px] px-2 py-0.5 rounded bg-white/5 edith-subtitle"
                  >
                    {String(p.pattern)}{' '}
                    <span className="text-emerald-400">
                      {Math.round(Number(p.win_rate ?? 0) * 100)}%
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="edith-panel edith-scan-wrap p-4 mb-6">
          <div className="jarvis-scan-line" aria-hidden />
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2 mb-3">
            <TrendingUp size={16} style={{ color: 'var(--edith-cyan)' }} />
            Symbol Math
            <span className="text-[10px] edith-subtitle font-normal normal-case tracking-normal">
              · {desk?.symbol_math?.symbol_count ?? 0} profiles · repeatable swings &amp; trends
            </span>
          </h2>
          <p className="text-xs edith-subtitle mb-3">
            Learns how each symbol moves from candle history + your closed trades — swing size,
            trend vs range, best hours, and per-symbol profit targets. No price predictions.
          </p>
          {symbolProfiles.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs edith-subtitle">
                <thead>
                  <tr className="text-left border-b border-white/10">
                    <th className="pb-2 pr-3 edith-label">Symbol</th>
                    <th className="pb-2 pr-3 edith-label">Style</th>
                    <th className="pb-2 pr-3 edith-label">Swing</th>
                    <th className="pb-2 pr-3 edith-label">Repeat</th>
                    <th className="pb-2 pr-3 edith-label">Book WR</th>
                    <th className="pb-2 pr-3 edith-label">Min profit</th>
                    <th className="pb-2 edith-label">Target</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolProfiles.map((row) => (
                    <tr key={row.symbol} className="border-b border-white/5">
                      <td className="py-1.5 pr-3 edith-value">{row.symbol}</td>
                      <td className="py-1.5 pr-3">{row.style ?? '—'}</td>
                      <td className="py-1.5 pr-3">
                        {row.swing_pct != null ? `${(Number(row.swing_pct) * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="py-1.5 pr-3">
                        {row.repeatability != null
                          ? `${Math.round(Number(row.repeatability) * 100)}%`
                          : '—'}
                      </td>
                      <td className="py-1.5 pr-3">
                        {row.samples
                          ? `${Math.round(Number(row.win_rate ?? 0) * 100)}% (${row.samples}n)`
                          : '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-emerald-400">
                        {row.min_profit_pct != null
                          ? `${(Number(row.min_profit_pct) * 100).toFixed(1)}%`
                          : '—'}
                      </td>
                      <td className="py-1.5">
                        {row.target_move_pct != null
                          ? `${(Number(row.target_move_pct) * 100).toFixed(1)}%`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="text-[10px] edith-subtitle mt-3 space-y-1">
                {symbolProfiles.slice(0, 4).map((row) =>
                  row.playbook_hint ? (
                    <li key={`${row.symbol}-hint`}>
                      · <span className="edith-value">{row.symbol}</span>: {row.playbook_hint}
                    </li>
                  ) : null,
                )}
              </ul>
            </div>
          ) : (
            <p className="text-xs edith-subtitle">
              No profiles yet — click Learn Symbols (runs automatically every learning-agent tick).
            </p>
          )}
        </section>

        <section className="edith-panel edith-scan-wrap p-4 mb-6">
          <div className="jarvis-scan-line" aria-hidden />
          <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2 mb-3">
            <Brain size={16} style={{ color: 'var(--edith-cyan)' }} />
            Market Genius Sweep
            <span className="text-[10px] edith-subtitle font-normal normal-case tracking-normal">
              · {genius?.tested ?? 0} backtests · {genius?.pass_rate_pct ?? '—'}% pass · gate WR{' '}
              {Math.round(Number(genius?.effective_min_win_rate ?? 0.42) * 100)}%
            </span>
          </h2>
          <p className="text-xs edith-subtitle mb-3">
            Systematic Nautilus backtests across whitelist symbols × strategies. Winners promote to
            entry gates; losers get blocked. No price predictions — only what historically worked.
          </p>

          {(playbook?.active || (playbook?.plan?.length ?? 0) > 0) && (
            <div className="mb-4 p-3 rounded border border-emerald-500/30 bg-emerald-500/5">
              <div className="text-xs edith-label mb-1 uppercase tracking-wider text-emerald-400">
                Live playbook {playbook?.active ? 'ACTIVE' : 'idle'}
              </div>
              <ul className="text-xs edith-subtitle space-y-1">
                {(playbook?.plan ?? []).map((line) => (
                  <li key={line}>· {line}</li>
                ))}
              </ul>
              {playbook?.tier1_symbols?.length ? (
                <p className="text-[10px] edith-subtitle mt-2">
                  Tier-1 only: {playbook.tier1_symbols.join(', ')}
                </p>
              ) : null}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs edith-label mb-2 uppercase tracking-wider text-emerald-400">
                Works (passes gate)
              </div>
              {geniusWorks.length > 0 ? (
                <ul className="space-y-1.5 max-h-52 overflow-y-auto">
                  {geniusWorks.map((row) => (
                    <li
                      key={`${row.symbol}-${row.strategy}`}
                      className="text-xs flex justify-between gap-2 edith-subtitle border-b border-white/5 pb-1"
                    >
                      <span className="edith-value">
                        {row.symbol} · {row.strategy}
                      </span>
                      <span className="text-emerald-400 shrink-0">
                        {Math.round(Number(row.win_rate ?? 0) * 100)}% · ${Number(row.total_pnl ?? 0).toFixed(0)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs edith-subtitle">
                  No sweep yet — click Run Genius Sweep (takes 1–3 min).
                </p>
              )}
            </div>
            <div>
              <div className="text-xs edith-label mb-2 uppercase tracking-wider text-rose-400">
                Doesn&apos;t work (blocked)
              </div>
              {geniusFails.length > 0 ? (
                <ul className="space-y-1.5 max-h-52 overflow-y-auto">
                  {geniusFails.map((row) => (
                    <li
                      key={`${row.symbol}-${row.strategy}-f`}
                      className="text-xs flex justify-between gap-2 edith-subtitle border-b border-white/5 pb-1"
                      title={row.gate_reason}
                    >
                      <span className="edith-value">
                        {row.symbol} · {row.strategy}
                      </span>
                      <span className="text-rose-400 shrink-0">
                        {Math.round(Number(row.win_rate ?? 0) * 100)}%
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs edith-subtitle">Failures populate after first sweep.</p>
              )}
            </div>
          </div>
          {(genius?.genius_notes?.length ?? 0) > 0 && (
            <ul className="text-xs edith-subtitle mt-3 space-y-1 border-t border-white/10 pt-3">
              {genius!.genius_notes!.map((n) => (
                <li key={n}>· {n}</li>
              ))}
            </ul>
          )}
        </section>

        {(desk?.desk_notes?.length ?? 0) > 0 && (
          <section className="edith-panel p-4">
            <h2 className="text-xs edith-label mb-2 uppercase tracking-wider">Desk notes</h2>
            <ul className="text-xs edith-subtitle space-y-1">
              {desk!.desk_notes!.map((note) => (
                <li key={note}>· {note}</li>
              ))}
            </ul>
            <p className="text-[10px] edith-subtitle mt-3 opacity-70">
              Agents: {desk?.agents?.running ? 'learning daemon ON' : 'learning daemon idle'} ·
              Nautilus passed-trade WR {String(edges?.nautilus?.passed_win_rate_pct ?? 0)}%
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
