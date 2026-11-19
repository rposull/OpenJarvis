import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';

import {

  RefreshCw,

  TrendingUp,

  Flame,

  Briefcase,

  ExternalLink,

  Radio,

  Bell,

  Search,

  Crosshair,

  Radar,

  LineChart,

  Activity,

} from 'lucide-react';

import { TradingViewChart } from '../components/Trading/TradingViewChart';
import { TradingViewLinkPanel } from '../components/Trading/TradingViewLinkPanel';

import {

  executeTradingViewAlert,

  fetchTradingAlerts,

  fetchTradingAutoStatus,

  fetchTradingAutomationStatus,

  fetchTradingConfig,

  fetchTradingHotSymbols,

  fetchTradingLearningSummary,

  fetchTradingPositions,

  fetchTradingScoutFeed,

  fetchTradingScoutStatus,

  fetchNautilusLearner,

  validateNautilusSetup,

  fetchTradingStatus,

  fetchTradingPnl,

  fetchTradingSymbolMap,

  submitTradingPaperOrder,

  tradingViewChartUrl,

  type TradingAlert,

  type TradingAutoStatus,

  type TradingAutomationStatus,

  type TradingConfig,

  type TradingHotCandidate,

  type TradingLearningSummary,

  type TradingPosition,

  type TradingPnlSummary,

  type TradingStatus,

  type MarketScoutSetup,

  type MarketScoutStatus,

} from '../lib/api';

import { useAppStore } from '../lib/store';

import '../styles/trading-edith.css';



function winProbClass(pct: number | undefined): string {

  if (pct == null) return 'edith-win';

  return pct < 50 ? 'edith-win edith-win-low' : 'edith-win';

}



function formatAlertTime(ts: number): string {

  return new Date(ts * 1000).toLocaleTimeString();

}



function fmtUsd(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}$${Math.abs(n).toFixed(2)}`;
}

function fmtPct(n: number | undefined | null, signed = false): string {
  if (n == null || Number.isNaN(n)) return '—';
  const prefix = signed && n > 0 ? '+' : '';
  return `${prefix}${n.toFixed(2)}%`;
}

function tradeStatusClass(status?: string): string {

  if (status === 'executed' || status === 'filled') return 'edith-alert-status-ok';

  if (status === 'queued') return 'edith-alert-status-queued';

  if (status === 'rejected' || status === 'failed') return 'edith-alert-status-error';

  return 'edith-alert-status-pending';

}



const STOCK_EXCHANGES = new Set(['NASDAQ', 'NYSE', 'AMEX', 'OTC', 'BATS', 'ARCA']);

function isStockTvSymbol(tv: string): boolean {
  const trimmed = tv.trim().toUpperCase();
  if (!trimmed) return false;
  if (trimmed.includes(':')) {
    return STOCK_EXCHANGES.has(trimmed.split(':', 1)[0]);
  }
  if (trimmed.includes('-')) return false;
  return /^[A-Z]{1,5}$/.test(trimmed);
}

function normalizeTvInput(raw: string): string {

  const trimmed = raw.trim().toUpperCase();

  if (!trimmed) return '';

  if (trimmed.includes(':')) return trimmed;

  if (trimmed.includes('-')) {

    const [base, quote] = trimmed.split('-', 2);

    return `COINBASE:${base}${quote}`;

  }

  if (/^[A-Z]{1,5}$/.test(trimmed)) return `NASDAQ:${trimmed}`;

  return trimmed;

}



export function TradingPage() {

  const settings = useAppStore((s) => s.settings);

  const chartTheme = settings.theme === 'light' ? 'light' : 'dark';



  const [status, setStatus] = useState<TradingStatus | null>(null);

  const [pnl, setPnl] = useState<TradingPnlSummary | null>(null);

  const [positions, setPositions] = useState<TradingPosition[]>([]);

  const [hotSymbols, setHotSymbols] = useState<TradingHotCandidate[]>([]);

  const [config, setConfig] = useState<TradingConfig | null>(null);

  const [automation, setAutomation] = useState<TradingAutomationStatus | null>(null);

  const [autoStatus, setAutoStatus] = useState<TradingAutoStatus | null>(null);

  const [learning, setLearning] = useState<TradingLearningSummary | null>(null);

  const [alerts, setAlerts] = useState<TradingAlert[]>([]);

  const [scoutFeed, setScoutFeed] = useState<MarketScoutSetup[]>([]);

  const [scoutStatus, setScoutStatus] = useState<MarketScoutStatus | null>(null);

  const [scoutAgreement, setScoutAgreement] = useState<Set<string>>(new Set());

  const [selectedSymbol, setSelectedSymbol] = useState('');

  const [symbolInput, setSymbolInput] = useState('');

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState('');

  const [orderFeedback, setOrderFeedback] = useState('');

  const [orderError, setOrderError] = useState(false);

  const [orderingSymbol, setOrderingSymbol] = useState('');

  const [nautilusValidating, setNautilusValidating] = useState('');

  const [nautilusLearner, setNautilusLearner] = useState<Record<string, unknown> | null>(null);

  const lastAlertTs = useRef(0);



  const refresh = useCallback(async () => {

    setLoading(true);

    setError('');

    try {

      const [st, pnlData, pos, hot, cfg, auto, autoTr, alertData, learn, scouts, scoutSt, nautLearner] = await Promise.all([

        fetchTradingStatus(),

        fetchTradingPnl().catch(() => null),

        fetchTradingPositions(),

        fetchTradingHotSymbols(),

        fetchTradingConfig(),

        fetchTradingAutomationStatus(),

        fetchTradingAutoStatus().catch(() => null),

        fetchTradingAlerts(),

        fetchTradingLearningSummary().catch(() => ({ available: false })),

        fetchTradingScoutFeed().catch(() => ({ setups: [], hot_agreement: [], count: 0 })),

        fetchTradingScoutStatus().catch(() => null),

        fetchNautilusLearner().catch(() => null),

      ]);

      setStatus(st);

      setPnl(pnlData || st.pnl || null);

      setPositions(pos.positions);

      setHotSymbols(hot.candidates);

      setConfig(cfg);

      setAutomation(auto);

      setAutoStatus(autoTr);

      setLearning(learn);

      setAlerts(alertData.alerts);

      setScoutFeed(scouts.setups || []);

      setScoutStatus(scoutSt);

      setScoutAgreement(new Set(scouts.hot_agreement || []));

      setNautilusLearner(nautLearner?.learner ?? autoTr?.nautilus?.learner ?? null);



      const latest = alertData.alerts[0];

      if (

        latest

        && cfg.auto_switch_chart

        && latest.tradingview_symbol

        && latest.received_at > lastAlertTs.current

      ) {

        lastAlertTs.current = latest.received_at;

        setSelectedSymbol(latest.tradingview_symbol);

      } else {

        setSelectedSymbol((prev) => {

          if (prev) return prev;

          if (pos.positions[0]?.tradingview_symbol) return pos.positions[0].tradingview_symbol;

          if (hot.candidates[0]?.tradingview_symbol) return hot.candidates[0].tradingview_symbol;

          return cfg.default_symbol;

        });

      }

    } catch (e) {

      setError(e instanceof Error ? e.message : 'Failed to load trading data');

    } finally {

      setLoading(false);

    }

  }, []);



  const refreshAlerts = useCallback(async () => {

    try {

      const [alertData, auto] = await Promise.all([

        fetchTradingAlerts(),

        fetchTradingAutomationStatus(),

      ]);

      setAlerts(alertData.alerts);

      setAutomation(auto);

      const latest = alertData.alerts[0];

      if (

        latest

        && config?.auto_switch_chart

        && latest.tradingview_symbol

        && latest.received_at > lastAlertTs.current

      ) {

        lastAlertTs.current = latest.received_at;

        setSelectedSymbol(latest.tradingview_symbol);

      }

    } catch {

      /* non-fatal poll */

    }

  }, [config?.auto_switch_chart]);



  useEffect(() => {

    void refresh();

    const timer = setInterval(() => void refresh(), 15000);

    return () => clearInterval(timer);

  }, [refresh]);



  useEffect(() => {

    const timer = setInterval(() => void refreshAlerts(), 5000);

    return () => clearInterval(timer);

  }, [refreshAlerts]);



  const handlePaperOrder = useCallback(async (symbol: string, action: 'buy' | 'sell', tvSymbol?: string) => {

    setOrderingSymbol(symbol);

    setOrderFeedback('');

    setOrderError(false);

    try {

      let internal = symbol;

      let market: string | undefined;

      let tradingview_symbol = tvSymbol || symbol;

      try {

        const mapped = await fetchTradingSymbolMap(tradingview_symbol);

        internal = mapped.symbol || symbol;

        market = mapped.market;

        tradingview_symbol = mapped.tradingview_symbol || tradingview_symbol;

      } catch {

        /* use raw symbol */

      }

      const result = await submitTradingPaperOrder(internal, action, {

        market,

        tradingview_symbol,

        source: tvSymbol ? 'ui_chart_symbol' : 'ui_hot_symbol',

      });

      setOrderFeedback(result.message || `Paper ${action} submitted for ${internal}`);

      setOrderError(false);

      await refresh();

    } catch (e) {

      setOrderFeedback(e instanceof Error ? e.message : 'Order failed');

      setOrderError(true);

    } finally {

      setOrderingSymbol('');

    }

  }, [refresh]);



  const selectSymbol = useCallback((tv: string) => {
    if (!tv) return;
    setSelectedSymbol(tv);
  }, []);

  const handleChartSymbolChange = useCallback((tv: string) => {
    selectSymbol(tv);
  }, [selectSymbol]);

  useEffect(() => {
    if (selectedSymbol) {
      setSymbolInput(selectedSymbol);
    }
  }, [selectedSymbol]);

  const handleSymbolSubmit = useCallback(async () => {

    const tv = normalizeTvInput(symbolInput);

    if (!tv) return;

    try {

      const mapped = await fetchTradingSymbolMap(tv);

      selectSymbol(mapped.tradingview_symbol || tv);

    } catch {

      selectSymbol(tv);

    }

  }, [symbolInput, selectSymbol]);



  const handleExecuteAlert = useCallback(async (alert: TradingAlert) => {

    setOrderFeedback('');

    setOrderError(false);

    try {

      const result = await executeTradingViewAlert(alert.tradingview_symbol);

      setOrderFeedback(result.order?.message || `Alert executed: ${alert.tradingview_symbol}`);

      await refresh();

    } catch (e) {

      setOrderFeedback(e instanceof Error ? e.message : 'Execute alert failed');

      setOrderError(true);

    }

  }, [refresh]);



  const session = status?.session;

  const pnlData = pnl || status?.pnl;

  const marketPnl = pnlData?.markets || status?.markets;

  const chartSymbol = selectedSymbol || config?.default_symbol || 'COINBASE:BTCUSD';

  const chartInterval = config?.interval || '5';

  const paperMode = session?.mode || 'PAPER_ONLY';
  const stocksPaused = pnlData?.alpaca?.stock_gates?.stocks_enabled === false;
  const chartIsStock = isStockTvSymbol(chartSymbol);



  const symbolButtons = useMemo(() => {

    const items: Array<{ label: string; tv: string; kind: 'position' | 'hot' | 'alert' | 'stock' }> = [];

    const seen = new Set<string>();

    const stockPicks = config?.example_stock_symbols || [];
    for (const s of stockPicks) {
      if (!s.tradingview_symbol || seen.has(s.tradingview_symbol)) continue;
      seen.add(s.tradingview_symbol);
      items.push({ label: s.symbol, tv: s.tradingview_symbol, kind: 'stock' });
    }

    for (const p of positions) {

      if (!p.tradingview_symbol || seen.has(p.tradingview_symbol)) continue;

      seen.add(p.tradingview_symbol);

      items.push({ label: p.symbol, tv: p.tradingview_symbol, kind: 'position' });

    }

    for (const h of hotSymbols) {

      if (!h.tradingview_symbol || seen.has(h.tradingview_symbol)) continue;

      seen.add(h.tradingview_symbol);

      items.push({ label: h.symbol, tv: h.tradingview_symbol, kind: 'hot' });

    }

    for (const a of alerts.slice(0, 5)) {

      if (!a.tradingview_symbol || seen.has(a.tradingview_symbol)) continue;

      seen.add(a.tradingview_symbol);

      items.push({

        label: a.internal_symbol || a.tradingview_symbol,

        tv: a.tradingview_symbol,

        kind: 'alert',

      });

    }

    return items;

  }, [positions, hotSymbols, alerts, config?.example_stock_symbols]);



  const scoutScanLabel = useMemo(() => {
    if (!scoutStatus?.updated_at) return 'awaiting first scan';
    const ago = Math.max(0, Math.floor(Date.now() / 1000 - scoutStatus.updated_at));
    if (ago < 60) return `${ago}s ago`;
    return `${Math.floor(ago / 60)}m ago`;
  }, [scoutStatus?.updated_at]);

  const traderNautilusLearner = useMemo(
    () => nautilusLearner ?? autoStatus?.nautilus?.learner ?? null,
    [nautilusLearner, autoStatus?.nautilus?.learner],
  );

  const runHotNautilusBacktest = useCallback(async (h: (typeof hotSymbols)[number]) => {
    setNautilusValidating(h.symbol);
    setOrderError(false);
    setOrderFeedback('');
    try {
      const updated = await validateNautilusSetup({
        symbol: h.symbol,
        direction: h.direction || 'long',
        pattern: h.pattern || null,
        label: h.pattern || 'hot_symbol',
        market: 'crypto',
        force_refresh: true,
      });
      setHotSymbols((rows) =>
        rows.map((row) =>
          row.symbol === h.symbol
            ? { ...row, nautilus_backtest: updated.nautilus_backtest }
            : row,
        ),
      );
      const nb = updated.nautilus_backtest;
      setOrderFeedback(
        nb?.passed
          ? `Nautilus PASS — ${h.symbol} WR ${Math.round((nb.win_rate ?? 0) * 100)}%`
          : `Nautilus FAIL — ${h.symbol}: ${nb?.gate_reason || nb?.error || 'gate failed'}`,
      );
    } catch (err) {
      setOrderError(true);
      setOrderFeedback(err instanceof Error ? err.message : 'Nautilus backtest failed');
    } finally {
      setNautilusValidating('');
    }
  }, []);



  return (

    <div className="flex-1 overflow-y-auto px-6 py-10 edith-trading">

      <div className="cosmos-layer cosmos-nebula" aria-hidden />
      <div className="cosmos-layer cosmos-aurora" aria-hidden />
      <div className="cosmos-layer cosmos-stars" aria-hidden />
      <div className="cosmos-layer cosmos-tree-system" aria-hidden>
        <svg className="cosmos-tree-svg" viewBox="0 0 500 500" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="cosmos-trunk-grad" x1="50%" y1="100%" x2="50%" y2="0%">
              <stop offset="0%" stopColor="rgba(92,225,255,0.95)" />
              <stop offset="55%" stopColor="rgba(179,136,255,0.65)" />
              <stop offset="100%" stopColor="rgba(255,106,213,0.45)" />
            </linearGradient>
            <linearGradient id="cosmos-limb-grad" x1="50%" y1="100%" x2="50%" y2="0%">
              <stop offset="0%" stopColor="rgba(92,225,255,0.75)" />
              <stop offset="100%" stopColor="rgba(179,136,255,0.3)" />
            </linearGradient>
            <filter id="cosmos-tree-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <g className="cosmos-tree" filter="url(#cosmos-tree-glow)">
            {/* trunk */}
            <path className="cosmos-tree-trunk" d="M250,268 Q252,248 250,228 Q248,208 250,188" />
            {/* crown — primary limbs */}
            <path className="cosmos-tree-limb cosmos-tree-limb-l" d="M250,210 Q215,198 178,178 Q148,162 115,142" />
            <path className="cosmos-tree-limb cosmos-tree-limb-r" d="M250,210 Q285,198 322,178 Q352,162 385,142" />
            <path className="cosmos-tree-limb cosmos-tree-limb-c" d="M250,210 Q248,178 246,148 Q244,118 242,88" />
            {/* secondary branches — left */}
            <path className="cosmos-tree-branch" d="M178,178 Q158,158 138,138" />
            <path className="cosmos-tree-branch" d="M178,178 Q168,152 152,128" />
            <path className="cosmos-tree-branch" d="M115,142 Q98,122 82,105" />
            <path className="cosmos-tree-branch" d="M115,142 Q108,118 98,96" />
            {/* secondary branches — right */}
            <path className="cosmos-tree-branch" d="M322,178 Q342,158 362,138" />
            <path className="cosmos-tree-branch" d="M322,178 Q332,152 348,128" />
            <path className="cosmos-tree-branch" d="M385,142 Q402,122 418,105" />
            <path className="cosmos-tree-branch" d="M385,142 Q392,118 402,96" />
            {/* secondary branches — center */}
            <path className="cosmos-tree-branch" d="M246,148 Q232,128 218,108" />
            <path className="cosmos-tree-branch" d="M246,148 Q258,128 272,108" />
            <path className="cosmos-tree-branch" d="M242,88 Q228,72 214,58" />
            <path className="cosmos-tree-branch" d="M242,88 Q256,72 270,58" />
            {/* tertiary twigs */}
            <path className="cosmos-tree-twig" d="M138,138 Q128,128 118,118" />
            <path className="cosmos-tree-twig" d="M152,128 Q142,115 132,102" />
            <path className="cosmos-tree-twig" d="M362,138 Q372,128 382,118" />
            <path className="cosmos-tree-twig" d="M348,128 Q358,115 368,102" />
            <path className="cosmos-tree-twig" d="M218,108 Q210,98 202,88" />
            <path className="cosmos-tree-twig" d="M272,108 Q280,98 288,88" />
            <path className="cosmos-tree-twig" d="M214,58 Q208,48 202,40" />
            <path className="cosmos-tree-twig" d="M270,58 Q276,48 282,40" />
            {/* downward root structure */}
            <path className="cosmos-tree-root cosmos-tree-root-main" d="M250,268 Q248,288 246,308 Q244,328 242,348" />
            <path className="cosmos-tree-root" d="M246,308 Q222,328 198,348 Q178,365 158,382" />
            <path className="cosmos-tree-root" d="M246,308 Q270,328 294,348 Q314,365 334,382" />
            <path className="cosmos-tree-root" d="M242,348 Q228,368 214,388 Q200,405 186,422" />
            <path className="cosmos-tree-root" d="M242,348 Q256,368 270,388 Q284,405 298,422" />
            <path className="cosmos-tree-root-fine" d="M198,348 Q188,362 178,376" />
            <path className="cosmos-tree-root-fine" d="M294,348 Q304,362 314,376" />
            <path className="cosmos-tree-root-fine" d="M214,388 Q206,400 198,412" />
            <path className="cosmos-tree-root-fine" d="M270,388 Q278,400 286,412" />
            {/* fork nodes */}
            <circle className="cosmos-tree-node" cx="250" cy="268" r="2.5" />
            <circle className="cosmos-tree-node" cx="250" cy="210" r="2" />
            <circle className="cosmos-tree-node" cx="178" cy="178" r="1.8" />
            <circle className="cosmos-tree-node" cx="322" cy="178" r="1.8" />
            <circle className="cosmos-tree-node" cx="246" cy="308" r="1.8" />
            {/* emit sparks at branch tips */}
            <circle className="cosmos-tree-spark" cx="82" cy="105" r="1.2" />
            <circle className="cosmos-tree-spark" cx="418" cy="105" r="1.2" />
            <circle className="cosmos-tree-spark" cx="202" cy="40" r="1.2" />
            <circle className="cosmos-tree-spark" cx="282" cy="40" r="1.2" />
            <circle className="cosmos-tree-spark" cx="186" cy="422" r="1.2" />
            <circle className="cosmos-tree-spark" cx="298" cy="422" r="1.2" />
          </g>
        </svg>
      </div>

      <div className="max-w-7xl mx-auto relative z-10">

        <header className="mb-6 flex items-start justify-between gap-4 edith-scan-wrap">

          <div className="jarvis-scan-line" aria-hidden />

          <div>

            <div className="edith-brand mb-1">J.A.R.V.I.S. · DEEP SPACE OPS</div>

            <h1 className="text-lg font-semibold flex items-center gap-2 edith-value">

              <Crosshair size={20} style={{ color: 'var(--edith-cyan)' }} />

              Cosmic Trading Command

            </h1>

            <p className="edith-subtitle mt-2 max-w-2xl">

              Scout agents · TradingView charts · webhook alerts · paper-only ({paperMode})
              {config?.trade_modes && (
                <>
                  {' '}
                  · Crypto: {config.trade_modes.crypto_trade_mode ?? 'spot_scalp'} spot
                  · Stocks: {config.trade_modes.stock_trade_mode ?? 'options'} only
                </>
              )}

            </p>

          </div>

          <button

            onClick={() => void refresh()}

            className="edith-refresh flex items-center gap-2 px-3 py-2 text-sm cursor-pointer"

            disabled={loading}

          >

            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />

            Refresh

          </button>

        </header>



        {automation && (

          <div className="mb-4 flex flex-wrap gap-2 text-xs">

            <span className={`edith-automation-badge ${automation.auto_execute ? 'active' : ''}`}>

              <Radio size={12} />

              Auto-execute {automation.auto_execute ? 'ON' : 'OFF'}

            </span>

            <span className="edith-automation-badge">

              Markets: {(automation.allowed_markets || []).join(', ')}

            </span>

            <span className={`edith-automation-badge ${automation.tunnel_active ? 'active' : ''}`}>

              Tunnel {automation.tunnel_active ? 'active' : 'local'}

            </span>

            {automation.live_session_running && (

              <span className="edith-automation-badge active">Live session running</span>

            )}

            {learning?.learning_active && learning.available && (

              <span className="edith-automation-badge active" title="Auto-learns after each close; mini-sweeps every 5 closes or 6h">

                Learning active

                {learning.refinement?.trades_since_last_sweep != null

                  ? ` (${learning.refinement.trades_since_last_sweep} since sweep)`

                  : ''}

              </span>

            )}

          </div>

        )}



        <Link
          to="/freqtrade"
          className="edith-panel edith-scan-wrap mb-6 p-4 block hover:border-cyan-500/30 transition-colors no-underline"
        >
          <div className="jarvis-scan-line" aria-hidden />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2">
              <LineChart size={16} style={{ color: 'var(--edith-cyan)' }} />
              Freqtrade
            </h2>
            <span className="text-xs edith-subtitle">Spot bot · dry-run · open dashboard →</span>
          </div>
        </Link>

        <Link
          to="/nautilus"
          className="edith-panel edith-scan-wrap mb-6 p-4 block hover:border-cyan-500/30 transition-colors no-underline"
        >
          <div className="jarvis-scan-line" aria-hidden />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2">
              <Activity size={16} style={{ color: 'var(--edith-cyan)' }} />
              Nautilus
            </h2>
            <span className="text-xs edith-subtitle">Backtest research worker · open dashboard →</span>
          </div>
        </Link>



        <div className="mb-6">
          <TradingViewLinkPanel />
        </div>



        <section className="edith-panel edith-holo-panel edith-scan-wrap mb-6 p-4">

            <div className="jarvis-scan-line" aria-hidden />

            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">

              <h2 className="text-sm font-semibold edith-value tracking-widest uppercase flex items-center gap-2">

                <Radar size={16} style={{ color: 'var(--edith-cyan)' }} />

                Market Scout Agents

              </h2>

              <span className="text-xs edith-subtitle">

                {scoutStatus?.running ? 'ACTIVE' : 'STANDBY'}

                {scoutStatus?.universe ? ` · scanning ${scoutStatus.universe} symbols` : ''}

                {scoutStatus?.setup_count ? ` · ${scoutStatus.setup_count} setups` : ''}

                {' · last scan '}{scoutScanLabel}

              </span>

            </div>

            <div className="edith-scout-grid mb-4">

              {(scoutStatus?.scouts || []).map((scout) => (

                <div

                  key={scout.id}

                  className={`edith-scout-card ${scout.status === 'scanning' ? 'active' : ''} ${(scout.setups_found || 0) > 0 ? 'setup-hit' : ''}`}

                >

                  <div className="edith-scout-id">{scout.id}</div>

                  <div className="edith-scout-meta">

                    {scout.status} · {scout.symbols_scanned ?? 0} sym · {scout.setups_found ?? 0} hits

                  </div>

                  {scout.note && (

                    <div className="edith-scout-meta mt-1 truncate" title={scout.note}>{scout.note}</div>

                  )}

                </div>

              ))}

              {!scoutStatus?.scouts?.length && (

                <p className="text-sm edith-subtitle col-span-full">

                  Scouts idle — run scripts/start-market-scouts.ps1 or start-live-trading.ps1

                </p>

              )}

            </div>

            {scoutFeed.length > 0 ? (

              <>

              {nautilusLearner && (

                <p className="text-xs edith-subtitle mb-2">

                  Nautilus auto-gate: min WR{' '}

                  {Math.round(Number(nautilusLearner.effective_min_win_rate ?? 0.42) * 100)}%

                  {nautilusLearner.passed_samples ? (

                    <> · live passed-trade WR {String(nautilusLearner.passed_win_rate_pct)}%</>

                  ) : null}

                  {' '}· backtests run on each scout scan

                </p>

              )}

              <ul className="space-y-2 max-h-56 overflow-y-auto">

                {scoutFeed.slice(0, 12).map((setup) => {

                  const confPct = Math.round((setup.confidence || 0) * 100);

                  const isAlert = (setup.confidence || 0) >= 0.65;

                  const nb = setup.nautilus_backtest;

                  const nbPass = nb?.passed === true;

                  const nbFail = nb && nb.passed === false;

                  return (

                    <li key={`${setup.symbol}-${setup.label}`}>

                      <div

                        className={`edith-row edith-setup-row w-full text-left px-3 py-2 text-sm ${isAlert ? 'edith-setup-alert' : ''} ${chartSymbol === setup.tradingview_symbol ? 'edith-row-active' : ''}`}

                      >

                        <button

                          type="button"

                          onClick={() => selectSymbol(setup.tradingview_symbol)}

                          className="w-full text-left cursor-pointer"

                        >

                          <div className="flex justify-between gap-2 items-center">

                            <span className="font-medium edith-value">{setup.symbol}</span>

                            <span className={`edith-setup-confidence ${confPct >= 70 ? 'high' : ''}`}>

                              {confPct}% · {setup.direction}

                            </span>

                          </div>

                          <div className="text-xs mt-1 edith-subtitle">{setup.label}</div>

                          <div className="text-xs mt-1 edith-subtitle truncate">

                            {(setup.tools || []).join(' · ')}

                          </div>

                        </button>

                        <div className="flex items-center justify-between gap-2 mt-2">

                          {nb ? (

                            <span className={`text-xs ${nbPass ? 'text-emerald-400' : nbFail ? 'text-rose-400' : 'edith-subtitle'}`}>

                              Nautilus {nbPass ? 'PASS' : nbFail ? 'FAIL' : '—'}

                              {nb.win_rate != null ? ` · ${Math.round(nb.win_rate * 100)}% WR` : ''}

                              {nb.total_pnl != null ? ` · ${nb.total_pnl >= 0 ? '+' : ''}$${Number(nb.total_pnl).toFixed(0)}` : ''}

                            </span>

                          ) : (

                            <span className="text-xs edith-subtitle">Nautilus not run</span>

                          )}

                          <button

                            type="button"

                            className="edith-btn edith-btn-sm edith-btn-ghost text-xs"

                            disabled={nautilusValidating === setup.symbol}

                            onClick={async (e) => {

                              e.stopPropagation();

                              setNautilusValidating(setup.symbol);

                              try {

                                const updated = await validateNautilusSetup({

                                  symbol: setup.symbol,

                                  direction: setup.direction,

                                  pattern: setup.pattern,

                                  label: setup.label,

                                  market: setup.market,

                                  force_refresh: true,

                                });

                                setScoutFeed((prev) =>

                                  prev.map((row) =>

                                    row.symbol === setup.symbol && row.label === setup.label

                                      ? { ...row, nautilus_backtest: updated.nautilus_backtest }

                                      : row,

                                  ),

                                );

                              } catch (err) {

                                setOrderError(true);

                                setOrderFeedback(err instanceof Error ? err.message : 'Nautilus backtest failed');

                              } finally {

                                setNautilusValidating('');

                              }

                            }}

                          >

                            {nautilusValidating === setup.symbol ? 'Running…' : 'Backtest'}

                          </button>

                        </div>

                      </div>

                    </li>

                  );

                })}

              </ul>

              </>

            ) : (

              <p className="text-sm edith-subtitle">No multi-tool setups detected yet.</p>

            )}

          </section>



        {error && (

          <div className="mb-4 px-4 py-3 edith-feedback edith-feedback-error text-sm">

            {error}

          </div>

        )}



        {orderFeedback && (

          <div

            className={`mb-4 px-4 py-3 text-sm ${orderError ? 'edith-feedback edith-feedback-error' : 'edith-feedback'}`}

          >

            {orderFeedback}

          </div>

        )}



        {pnlData?.available && (

          <section className="edith-pnl-hud edith-panel edith-scan-wrap mb-6 p-4">

            <div className="jarvis-scan-line" aria-hidden />

            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">

              <h2 className="text-sm font-semibold edith-value tracking-widest uppercase">

                Live P&amp;L · Paper Session

              </h2>

              <span className="text-xs edith-subtitle flex flex-wrap items-center gap-2">

                {autoStatus?.enabled && (

                  <span className="edith-alert-status-ok px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider">

                    AUTO: ON · {autoStatus.buys_today}B / {autoStatus.sells_today}S today

                  </span>

                )}

                {session?.running ? 'SESSION ACTIVE' : 'SESSION IDLE'} · {session?.mode || pnlData.mode || 'PAPER_ONLY'}

              </span>

            </div>

            {traderNautilusLearner && (
              <p className="text-xs edith-subtitle mb-3">
                Nautilus gate (trader + Freqtrade): min WR{' '}
                {Math.round(Number(traderNautilusLearner.effective_min_win_rate ?? 0.42) * 100)}%
                {traderNautilusLearner.passed_samples ? (
                  <> · live passed-trade WR {String(traderNautilusLearner.passed_win_rate_pct)}%</>
                ) : null}
                {' '}· hot symbols &amp; positions show PASS/FAIL
              </p>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">

              {[

                { label: 'Equity', value: fmtUsd(pnlData.equity ?? session?.equity), hero: true },

                { label: 'Return', value: fmtPct(pnlData.return_pct ?? session?.return_pct, true), hero: true },

                { label: 'Realized', value: fmtUsd(pnlData.realized_pnl ?? session?.realized_pnl, true) },

                { label: 'Session', value: fmtUsd(pnlData.session_pnl ?? session?.session_pnl, true) },

                { label: 'Today', value: fmtUsd(pnlData.today_pnl ?? session?.today_pnl, true) },

                { label: 'Open uPnL', value: fmtUsd(pnlData.unrealized_pnl ?? session?.unrealized_pnl, true) },

                { label: 'Win Rate', value: `${(pnlData.win_rate_pct ?? session?.win_rate_pct ?? 0).toFixed(1)}%` },

                { label: 'W / L', value: `${pnlData.wins ?? session?.wins ?? 0} / ${pnlData.losses ?? session?.losses ?? 0}` },

              ].map((item) => (

                <div key={item.label} className={`edith-stat px-3 py-2 ${item.hero ? 'edith-stat-hero' : ''}`}>

                  <div className="edith-label">{item.label}</div>

                  <div className="edith-value text-sm font-medium mt-1">{item.value}</div>

                </div>

              ))}

            </div>

            {marketPnl && (

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">

                {(['crypto', 'stocks'] as const).map((mkt) => {

                  const bucket = marketPnl[mkt];

                  if (!bucket) return null;

                  const hasActivity = (bucket.closed_trades ?? 0) > 0 || (bucket.open_positions ?? 0) > 0;

                  if (mkt === 'stocks' && !hasActivity) return null;

                  return (

                    <div key={mkt} className="edith-market-pnl px-3 py-2">

                      <div className="edith-label uppercase text-xs mb-1">{mkt}</div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs edith-subtitle">

                        <span>Realized {fmtUsd(bucket.realized_pnl, true)}</span>

                        <span>Open uPnL {fmtUsd(bucket.unrealized_pnl, true)}</span>

                        <span>{bucket.closed_trades ?? 0} closed</span>

                        <span>{(bucket.win_rate_pct ?? 0).toFixed(1)}% WR</span>

                      </div>

                    </div>

                  );

                })}

              </div>

            )}

            {pnlData.alpaca?.stock_gates?.stocks_enabled === false && (

              <p className="text-xs edith-subtitle mt-3">

                Stocks paused — TradingView crypto active

              </p>

            )}

            {pnlData.alpaca?.configured && pnlData.alpaca?.ok && (

              <p className="text-xs text-emerald-400 mt-3">

                Alpaca linked — live stock quotes &amp; bars

                {pnlData.alpaca.sample_quote?.price != null && (

                  <> ({pnlData.alpaca.sample_quote.symbol} ${pnlData.alpaca.sample_quote.price.toFixed(2)})</>

                )}

              </p>

            )}

            {pnlData.alpaca?.configured && !pnlData.alpaca?.ok && (

              <p className="text-xs text-red-400 mt-3">

                Alpaca error — {pnlData.alpaca.error || 'check paper API keys and restart Jarvis'}

              </p>

            )}

            {pnlData.alpaca?.keys_file_exists && !pnlData.alpaca?.configured && (

              <p className="text-xs text-amber-400 mt-3">

                Alpaca keys file found — paste paper keys in ~/.openjarvis/alpaca-keys.txt then restart Jarvis

              </p>

            )}

            {!pnlData.alpaca?.keys_file_exists && !pnlData.alpaca?.configured && (

              <p className="text-xs text-amber-400 mt-3">

                Alpaca not set up — run scripts\setup-alpaca-keys.ps1 or add ~/.openjarvis/alpaca-keys.txt

              </p>

            )}

          </section>

        )}



        <div className="mb-3 flex flex-wrap items-center gap-2">

          <div className="edith-symbol-search flex items-center gap-2 flex-1 min-w-[240px]">

            <Search size={14} className="edith-muted-icon" />

            <input

              type="text"

              value={symbolInput}

              onChange={(e) => setSymbolInput(e.target.value)}

              onKeyDown={(e) => e.key === 'Enter' && void handleSymbolSubmit()}

              placeholder="Any TV symbol: NASDAQ:AAPL, BINANCE:BTCUSDT, DOGE-USDC"

              className="edith-symbol-input flex-1"

            />

            <button

              type="button"

              className="edith-chip px-2 py-1 cursor-pointer"

              onClick={() => void handleSymbolSubmit()}

            >

              Load

            </button>

          </div>

          <a

            href={tradingViewChartUrl(chartSymbol)}

            target="_blank"

            rel="noopener noreferrer"

            className="edith-external-link flex items-center gap-1.5 px-3 py-1.5 text-xs"

          >

            <ExternalLink size={12} />

            Open in TradingView

          </a>

        </div>



        <div className="mb-3 flex flex-wrap gap-2">

          {symbolButtons.map((item) => {

            const active = chartSymbol === item.tv;

            return (

              <button

                key={item.tv}

                onClick={() => selectSymbol(item.tv)}

                className={`edith-chip flex items-center gap-1.5 px-3 py-1.5 cursor-pointer ${active ? 'edith-chip-active' : ''}`}

              >

                {item.kind === 'position' && <Briefcase size={12} />}

                {item.kind === 'hot' && <Flame size={12} />}

                {item.kind === 'alert' && <Bell size={12} />}

                {item.kind === 'stock' && <TrendingUp size={12} />}

                {item.label}

              </button>

            );

          })}

        </div>



        <div className="mb-2 flex flex-wrap items-center gap-2">

          <div className="text-xs edith-label">

            {chartSymbol} · {chartInterval}m · Advanced Chart

          </div>

          <div className="flex gap-2 ml-auto">

            <button

              type="button"

              className="edith-btn-buy px-3 py-1 text-xs"

              disabled={orderingSymbol === chartSymbol || (stocksPaused && chartIsStock)}

              title={stocksPaused && chartIsStock ? 'Stocks paused — TradingView crypto active' : undefined}

              onClick={() => void handlePaperOrder(chartSymbol, 'buy', chartSymbol)}

            >

              {isStockTvSymbol(chartSymbol)
                ? 'Option Buy'
                : config?.trade_modes?.crypto_kind === 'spot'
                  ? 'Spot Buy'
                  : 'Paper Buy'}

            </button>

            <button

              type="button"

              className="edith-btn-sell px-3 py-1 text-xs"

              disabled={orderingSymbol === chartSymbol || (stocksPaused && chartIsStock)}

              title={stocksPaused && chartIsStock ? 'Stocks paused — TradingView crypto active' : undefined}

              onClick={() => void handlePaperOrder(chartSymbol, 'sell', chartSymbol)}

            >

              Paper Sell

            </button>

          </div>

        </div>



        <div className="edith-panel edith-scan-wrap edith-chart-panel">

          <div className="jarvis-scan-line" aria-hidden />

          <TradingViewChart

            symbol={chartSymbol}

            interval={chartInterval}

            theme={chartTheme}

            height={640}

            onSymbolChange={handleChartSymbolChange}

          />

        </div>



        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">

          <section className="edith-panel p-4">

            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2 edith-value">

              <Briefcase size={16} style={{ color: 'var(--edith-cyan)' }} />

              <span className="edith-label" style={{ fontSize: '0.75rem' }}>Open Positions</span>

            </h2>

            {positions.length === 0 ? (

              <p className="text-sm edith-subtitle">No open positions.</p>

            ) : (

              <ul className="space-y-2">

                {positions.map((p) => {

                  const nb = p.nautilus_backtest;

                  const nbPass = nb?.passed === true;

                  const nbFail = nb && nb.passed === false;

                  return (

                  <li key={`${p.n}-${p.symbol}`}>

                    <button

                      onClick={() => selectSymbol(p.tradingview_symbol)}

                      className={`edith-row w-full text-left px-3 py-2 text-sm cursor-pointer ${

                        chartSymbol === p.tradingview_symbol ? 'edith-row-active' : ''

                      }`}

                    >

                      <div className="font-medium edith-value">

                        #{p.n} {p.symbol} · {p.qty}

                        {nb ? (
                          <span
                            className={`ml-2 text-[10px] font-semibold ${nbPass ? 'text-emerald-400' : nbFail ? 'text-rose-400' : 'edith-subtitle'}`}
                          >
                            Nautilus {nbPass ? 'PASS' : nbFail ? 'FAIL' : '—'}
                          </span>
                        ) : null}

                      </div>

                      <div className="text-xs mt-1 edith-subtitle">

                        {p.bought_at ? `Bought ${p.bought_at}` : ''}

                        {p.bought_at ? ' · ' : ''}

                        Worth ${(p.market_value_usd ?? p.entry_cost_usd ?? (p.price != null ? p.price * 100 * 2 : 0)).toFixed(2)}

                        {p.entry_cost_usd != null ? ` · paid $${p.entry_cost_usd.toFixed(2)}` : ''}

                        {' · '}

                        {p.unrealized_pnl != null

                          ? `${p.unrealized_pnl >= 0 ? '+' : ''}$${p.unrealized_pnl.toFixed(2)} uPnL`

                          : (p.unrealized ?? '—')}

                        {p.bars_remaining != null ? ` · ${p.bars_remaining}b left` : ''}

                      </div>

                      {(p.exit_plan || p.note) && (

                        <div className="text-xs mt-0.5 edith-subtitle opacity-80">

                          {p.exit_plan ? `Exit: ${p.exit_plan}` : ''}

                          {p.exit_plan && p.note ? ' · ' : ''}

                          {p.note ? p.note.slice(0, 56) : ''}

                        </div>

                      )}

                    </button>

                  </li>

                  );

                })}

              </ul>

            )}

          </section>



          <section className="edith-panel p-4">

            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2 edith-value">

              <Flame size={16} style={{ color: 'var(--edith-cyan)' }} />

              <span className="edith-label" style={{ fontSize: '0.75rem' }}>Hot Symbols · Scanner</span>

            </h2>

            {hotSymbols.length === 0 ? (

              <p className="text-sm edith-subtitle">No scanner candidates.</p>

            ) : (

              <ul className="space-y-2 max-h-72 overflow-y-auto">

                {hotSymbols.slice(0, 12).map((h) => {

                  const winPct = h.win_prob_pct ?? (h.win_prob != null ? h.win_prob * 100 : undefined);

                  const busy = orderingSymbol === h.symbol;

                  const nb = h.nautilus_backtest;

                  const nbPass = nb?.passed === true;

                  const nbFail = nb && nb.passed === false;

                  return (

                    <li key={h.symbol}>

                      <div

                        className={`edith-row px-3 py-2 text-sm ${

                          chartSymbol === h.tradingview_symbol ? 'edith-row-active' : ''

                        }`}

                      >

                        <button

                          type="button"

                          onClick={() => selectSymbol(h.tradingview_symbol)}

                          className="w-full text-left cursor-pointer"

                        >

                          <div className="flex justify-between gap-2 items-center">

                            <span className="font-medium edith-value">{h.symbol}</span>

                            <span className="flex items-center gap-2">

                              {winPct != null && (

                                <span className={winProbClass(winPct)} title="Estimated win probability">

                                  Win {winPct.toFixed(0)}%

                                </span>

                              )}

                              {scoutAgreement.has(h.symbol) && (

                                <span className="edith-scout-badge" title="Scout agents agree">

                                  Scout

                                </span>

                              )}

                              {nb ? (
                                <span
                                  className={`text-[10px] font-semibold ${nbPass ? 'text-emerald-400' : nbFail ? 'text-rose-400' : 'edith-subtitle'}`}
                                  title={nb.gate_reason || undefined}
                                >
                                  Nautilus {nbPass ? 'PASS' : nbFail ? 'FAIL' : '—'}
                                </span>
                              ) : null}

                              <span className="text-xs edith-subtitle">

                                {h.spot_fmt ?? h.spot}

                              </span>

                            </span>

                          </div>

                          <div className="text-xs mt-1 edith-subtitle">

                            {h.pattern} · {h.direction} · {(Number(h.strength) * 100).toFixed(0)}%

                          </div>

                        </button>

                        <div className="flex gap-2 mt-2 justify-end">

                          <button
                            type="button"
                            className="edith-btn edith-btn-sm edith-btn-ghost"
                            disabled={nautilusValidating === h.symbol}
                            onClick={() => void runHotNautilusBacktest(h)}
                          >
                            {nautilusValidating === h.symbol ? 'Running…' : 'Backtest'}
                          </button>

                          <button

                            type="button"

                            className="edith-btn-buy"

                            disabled={busy}

                            onClick={() => void handlePaperOrder(h.symbol, 'buy', h.tradingview_symbol)}

                          >

                            Buy

                          </button>

                          <button

                            type="button"

                            className="edith-btn-sell"

                            disabled={busy}

                            onClick={() => void handlePaperOrder(h.symbol, 'sell', h.tradingview_symbol)}

                          >

                            Sell

                          </button>

                        </div>

                      </div>

                    </li>

                  );

                })}

              </ul>

            )}

          </section>



          <section className="edith-panel p-4">

            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2 edith-value">

              <Bell size={16} style={{ color: 'var(--edith-cyan)' }} />

              <span className="edith-label" style={{ fontSize: '0.75rem' }}>TradingView Alerts</span>

            </h2>

            {alerts.length === 0 ? (

              <p className="text-sm edith-subtitle">

                No alerts yet. Point TradingView webhooks at Jarvis to auto paper-trade.

              </p>

            ) : (

              <ul className="space-y-2 max-h-72 overflow-y-auto">

                {alerts.slice(0, 20).map((a, idx) => (

                  <li key={`${a.received_at}-${a.tradingview_symbol}-${idx}`}>

                    <div

                      className={`edith-row px-3 py-2 text-sm ${

                        chartSymbol === a.tradingview_symbol ? 'edith-row-active' : ''

                      }`}

                    >

                      <button

                        type="button"

                        onClick={() => selectSymbol(a.tradingview_symbol)}

                        className="w-full text-left cursor-pointer"

                      >

                        <div className="flex justify-between gap-2 items-center">

                          <span className="font-medium edith-value">{a.tradingview_symbol}</span>

                          <span className={`text-xs ${tradeStatusClass(a.trade_status)}`}>

                            {a.trade_status || 'received'}

                          </span>

                        </div>

                        <div className="text-xs mt-1 edith-subtitle">

                          {a.action?.toUpperCase() || '—'} · {a.market || '—'} · {formatAlertTime(a.received_at)}

                        </div>

                        {a.message && (

                          <div className="text-xs mt-1 edith-subtitle truncate" title={a.message}>

                            {a.message.slice(0, 80)}

                          </div>

                        )}

                      </button>

                      {(a.trade_status === 'rejected' || a.trade_status === 'no_action') && (

                        <div className="flex justify-end mt-2">

                          <button

                            type="button"

                            className="edith-btn-buy"

                            onClick={() => void handleExecuteAlert(a)}

                          >

                            Execute

                          </button>

                        </div>

                      )}

                    </div>

                  </li>

                ))}

              </ul>

            )}

          </section>

        </div>



        {config?.webhook_url && (

          <div className="text-xs mt-6 edith-subtitle space-y-1">

            <p>

              TradingView webhook (paper only):{' '}

              <code className="edith-code">{config.webhook_url}</code>

            </p>

            <p>

              Charts and alerts via TradingView · execution is simulated in Jarvis only.

              Supports all TV symbols (stocks + crypto).

            </p>

          </div>

        )}

      </div>

    </div>

  );

}

