import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { ExternalLink, LayoutGrid, LogIn, Maximize2 } from 'lucide-react';
import { TradingViewChart } from '../components/Trading/TradingViewChart';
import {
  fetchTradingConfig,
  jarvisTradingViewTabUrl,
  TRADINGVIEW_FULL_SITE_URL,
  tradingViewFullSiteChartUrl,
} from '../lib/api';

export function TradingViewPage() {
  const [params, setParams] = useSearchParams();
  const [defaultSymbol, setDefaultSymbol] = useState('COINBASE:BTCUSD');
  const [defaultInterval, setDefaultInterval] = useState('5');

  const symbol = (params.get('symbol') || defaultSymbol).trim();
  const interval = params.get('interval') || defaultInterval;

  useEffect(() => {
    fetchTradingConfig()
      .then((cfg) => {
        if (cfg.default_symbol) setDefaultSymbol(cfg.default_symbol);
        if (cfg.interval) setDefaultInterval(String(cfg.interval));
      })
      .catch(() => {});
  }, []);

  const jarvisTabUrl = useMemo(() => jarvisTradingViewTabUrl(symbol, interval), [symbol, interval]);
  const fullTvUrl = useMemo(() => tradingViewFullSiteChartUrl(symbol), [symbol]);

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#0b0f14]">
      <header
        className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-white/10"
        style={{ background: 'var(--color-bg-secondary, #111827)' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Maximize2 size={16} className="text-cyan-400 shrink-0" />
          <span className="text-sm font-medium edith-value truncate">{symbol}</span>
          <span className="text-[10px] edith-subtitle">· {interval}m</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Link to="/trading" className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1">
            <LayoutGrid size={14} />
            Jarvis Trading
          </Link>
          <a
            href={TRADINGVIEW_FULL_SITE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="edith-btn edith-btn-sm inline-flex items-center gap-1"
            title="Full tradingview.com — sign in there, then use full chart link"
          >
            <LogIn size={14} />
            Full site login
          </a>
          <a
            href={fullTvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1"
          >
            <ExternalLink size={14} />
            Full chart
          </a>
        </div>
      </header>

      <p className="shrink-0 px-3 py-1.5 text-[10px] edith-subtitle border-b border-white/5">
        <strong className="text-cyan-300/70 font-normal">Cursor full site:</strong>{' '}
        Run Task → Jarvis: TradingView full site (login) — sign in manually on tradingview.com.{' '}
        <strong className="text-cyan-300/70 font-normal">Embed:</strong> Simple Browser →{' '}
        <button
          type="button"
          className="text-cyan-300/90 underline underline-offset-2"
          onClick={() => void navigator.clipboard.writeText(jarvisTabUrl)}
        >
          {jarvisTabUrl}
        </button>
      </p>

      <div className="flex-1 min-h-0">
        <TradingViewChart
          symbol={symbol}
          interval={interval}
          height="100%"
          onSymbolChange={(next) => {
            const nextParams = new URLSearchParams(params);
            nextParams.set('symbol', next);
            setParams(nextParams, { replace: true });
          }}
        />
      </div>
    </div>
  );
}
