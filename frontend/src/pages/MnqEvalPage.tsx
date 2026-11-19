import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Crosshair, RefreshCw, Target, TrendingUp } from 'lucide-react';
import {
  fetchAlpacaStatus,
  fetchPropFirmEval,
  tradingViewChartUrl,
  type PropFirmEvalDesk,
} from '../lib/api';
import '../styles/trading-edith.css';

function pct(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
}

export function MnqEvalPage() {
  const [desk, setDesk] = useState<PropFirmEvalDesk | null>(null);
  const [alpacaOk, setAlpacaOk] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [evalDesk, alpaca] = await Promise.all([
        fetchPropFirmEval(),
        fetchAlpacaStatus().catch(() => null),
      ]);
      setDesk(evalDesk);
      setAlpacaOk(alpaca ? Boolean(alpaca.ok && alpaca.configured) : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load MNQ eval desk');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const ev = desk?.eval;
  const cfg = desk?.config;

  return (
    <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 edith-trading">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] mb-2" style={{ color: 'var(--edith-cyan)' }}>
              Eval practice · paper only
            </p>
            <h1 className="text-2xl font-semibold flex items-center gap-2" style={{ color: 'var(--edith-text)' }}>
              <Crosshair size={22} style={{ color: 'var(--edith-cyan)' }} />
              MNQ Bot
            </h1>
            <p className="text-sm mt-2 max-w-xl" style={{ color: 'var(--edith-muted)' }}>
              Prop-firm eval practice desk — pass-rate sims from your replay book, wired to the same paper stack as
              Alpaca. Not live futures order routing.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={tradingViewChartUrl('CME_MINI:MNQ1!')}
              target="_blank"
              rel="noreferrer"
              className="text-xs px-3 py-1.5 rounded-lg border"
              style={{ borderColor: 'var(--edith-border)', color: 'var(--edith-cyan)' }}
            >
              MNQ chart
            </a>
            <Link
              to="/trading"
              className="text-xs px-3 py-1.5 rounded-lg border"
              style={{ borderColor: 'var(--edith-border)', color: 'var(--edith-text)' }}
            >
              Alpaca paper
            </Link>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className="text-xs px-3 py-1.5 rounded-lg border inline-flex items-center gap-1.5"
              style={{ borderColor: 'var(--edith-border)', color: 'var(--edith-text)' }}
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="edith-panel p-3 mb-4 text-sm text-rose-300 border border-rose-500/30">{error}</div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <div className="edith-panel p-4">
            <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--edith-muted)' }}>
              Eval pass
            </p>
            <p className="text-2xl font-semibold" style={{ color: 'var(--edith-cyan)' }}>
              {pct(ev?.eval_pass_pct)}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--edith-muted)' }}>
              Target {pct(cfg?.target_pass_pct)} · {cfg?.enabled ? 'rules on' : 'rules off'}
            </p>
          </div>
          <div className="edith-panel p-4">
            <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--edith-muted)' }}>
              Combined payout
            </p>
            <p className="text-2xl font-semibold" style={{ color: 'var(--edith-text)' }}>
              {pct(ev?.combined_payout_chance_pct)}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--edith-muted)' }}>
              Pass → payout {pct(ev?.funded_payout_given_pass_pct)}
            </p>
          </div>
          <div className="edith-panel p-4">
            <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--edith-muted)' }}>
              Replay WR
            </p>
            <p className="text-2xl font-semibold" style={{ color: 'var(--edith-text)' }}>
              {pct(ev?.replay_sample?.win_rate_pct)}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--edith-muted)' }}>
              {ev?.replay_sample?.n_trades ?? '—'} trades · {ev?.simulations?.toLocaleString() ?? '—'} sims
            </p>
          </div>
          <div className="edith-panel p-4">
            <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--edith-muted)' }}>
              Alpaca paper
            </p>
            <p className="text-2xl font-semibold" style={{ color: alpacaOk ? '#6ee7b7' : 'var(--edith-muted)' }}>
              {alpacaOk == null ? '—' : alpacaOk ? 'OK' : 'Down'}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--edith-muted)' }}>
              Dashboard + Trading for the book
            </p>
          </div>
        </div>

        <div className="edith-panel p-5 mb-4">
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-2" style={{ color: 'var(--edith-cyan)' }}>
            <Target size={16} />
            Interpretation
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--edith-text)' }}>
            {ev?.interpretation ||
              (desk?.ok === false
                ? 'No prop_firm_eval.json yet — run the Monte Carlo script to populate this desk.'
                : loading
                  ? 'Loading…'
                  : 'Waiting for eval data.')}
          </p>
          {ev?.rules && (
            <p className="text-xs mt-3 font-mono" style={{ color: 'var(--edith-muted)' }}>
              ${Number(ev.rules.account_size || 0).toLocaleString()} account · +
              {((ev.rules.profit_target_pct || 0) * 100).toFixed(0)}% target ·{' '}
              {((ev.rules.max_daily_loss_pct || 0) * 100).toFixed(0)}% daily loss ·{' '}
              {((ev.rules.max_drawdown_pct || 0) * 100).toFixed(0)}% max DD
            </p>
          )}
        </div>

        <div className="edith-panel p-5">
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--edith-cyan)' }}>
            <TrendingUp size={16} />
            Practice loop
          </h2>
          <ol className="text-sm space-y-2 list-decimal pl-5" style={{ color: 'var(--edith-muted)' }}>
            <li>
              Watch setups on <Link to="/setup-scanner" style={{ color: 'var(--edith-cyan)' }}>Setup Scanner</Link> /
              TradingView MNQ.
            </li>
            <li>
              Paper path stays on <Link to="/" style={{ color: 'var(--edith-cyan)' }}>Alpaca Dash</Link> +{' '}
              <Link to="/trading" style={{ color: 'var(--edith-cyan)' }}>Trading</Link> (orders_enabled stays off unless
              you change trading.toml).
            </li>
            <li>
              Refresh this desk after{' '}
              <code className="text-[11px]">uv run python trading_research/scripts/run_prop_firm_eval.py</code> to
              update pass-rate odds.
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
