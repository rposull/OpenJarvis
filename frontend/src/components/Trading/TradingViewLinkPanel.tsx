import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, Link2, LogIn, Monitor, RefreshCw, Radio, User, X } from 'lucide-react';
import { Link } from 'react-router';
import {
  fetchTradingAlerts,
  fetchTradingViewLink,
  jarvisTradingViewTabUrl,
  saveTradingViewAccount,
  TRADINGVIEW_FULL_SITE_URL,
  tradingViewFullSiteChartUrl,
  type TradingAlert,
  type TradingViewLinkStatus,
} from '../../lib/api';
import { TradingViewChart } from './TradingViewChart';

function fmtTime(ts?: number | null): string {
  if (!ts) return '—';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return '—';
  }
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

interface TradingViewLinkPanelProps {
  compact?: boolean;
  className?: string;
}

export function TradingViewLinkPanel({ compact = false, className = '' }: TradingViewLinkPanelProps) {
  const [link, setLink] = useState<TradingViewLinkStatus | null>(null);
  const [alerts, setAlerts] = useState<TradingAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState<'url' | 'json' | 'cursor' | 'fullsite' | 'login' | null>(null);
  const [showSignIn, setShowSignIn] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [savingAccount, setSavingAccount] = useState(false);
  const [accountError, setAccountError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [linkData, alertData] = await Promise.all([
        fetchTradingViewLink(),
        fetchTradingAlerts(),
      ]);
      setLink(linkData);
      setDisplayName(linkData.account?.display_name || '');
      setAlerts(alertData.alerts || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load TradingView link status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const chartSymbol = `${link?.default_exchange || 'COINBASE'}:BTCUSD`;

  const handleCopy = async (kind: 'url' | 'json' | 'cursor' | 'fullsite' | 'login') => {
    if (!link && kind !== 'cursor' && kind !== 'login') return;
    const text =
      kind === 'url'
        ? link!.webhook_url
        : kind === 'login'
          ? TRADINGVIEW_FULL_SITE_URL
          : kind === 'fullsite'
            ? tradingViewFullSiteChartUrl(chartSymbol)
            : kind === 'cursor'
              ? jarvisTradingViewTabUrl(chartSymbol, String(link?.interval ?? '5'))
              : JSON.stringify(link!.alert_json_template, null, 2);
    const ok = await copyText(text);
    if (ok) {
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 2000);
    }
  };

  const handleConfirmLink = async () => {
    setSavingAccount(true);
    setAccountError('');
    try {
      await saveTradingViewAccount({
        action: 'link',
        display_name: displayName.trim() || 'TradingView user',
        confirmed_in_widget: true,
      });
      setShowSignIn(false);
      await refresh();
    } catch (e) {
      setAccountError(e instanceof Error ? e.message : 'Failed to save account link');
    } finally {
      setSavingAccount(false);
    }
  };

  const handleUnlink = async () => {
    setSavingAccount(true);
    setAccountError('');
    try {
      await saveTradingViewAccount({ action: 'unlink' });
      setDisplayName('');
      await refresh();
    } catch (e) {
      setAccountError(e instanceof Error ? e.message : 'Failed to unlink account');
    } finally {
      setSavingAccount(false);
    }
  };

  const templateJson = link ? JSON.stringify(link.alert_json_template, null, 2) : '';
  const accountLinked = link?.account_linked ?? link?.account?.linked ?? false;
  const webhookReady = link?.webhook_ready ?? link?.linked ?? false;

  return (
    <>
      <section className={`edith-panel p-4 ${className}`}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="text-sm font-semibold edith-value flex items-center gap-2">
            <Link2 size={16} style={{ color: 'var(--edith-cyan)' }} />
            TradingView
          </h2>
          <div className="flex items-center gap-2">
            {link && (
              <>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded border ${
                    accountLinked
                      ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                      : 'border-amber-500/40 text-amber-400 bg-amber-500/10'
                  }`}
                >
                  {accountLinked ? 'Account linked' : 'Not signed in'}
                </span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded border ${
                    webhookReady
                      ? 'border-cyan-500/40 text-cyan-300 bg-cyan-500/10'
                      : 'border-white/15 text-white/50 bg-white/5'
                  }`}
                >
                  Webhook {webhookReady ? 'ready' : 'setup needed'}
                </span>
              </>
            )}
            <button
              type="button"
              className="edith-btn edith-btn-sm edith-btn-ghost"
              onClick={() => void refresh()}
              disabled={loading}
              title="Refresh link status and alerts"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {(error || accountError) && (
          <p className="text-xs text-rose-400 mb-2">{error || accountError}</p>
        )}

        {link && (
          <div className="space-y-3 text-xs">
            <div className="rounded border border-white/10 bg-white/[0.03] p-3 space-y-2">
              <p className="edith-subtitle leading-relaxed">
                TradingView does not expose candle or trade APIs to third-party apps. Jarvis uses{' '}
                <strong className="text-cyan-300/90 font-normal">webhooks for alerts</strong> and your{' '}
                <strong className="text-cyan-300/90 font-normal">browser TV session</strong> for charts
                (saved layouts, watchlists, broker panel if you connect a broker on tradingview.com).
              </p>
              {accountLinked ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 edith-value">
                    <User size={14} className="text-emerald-400" />
                    <span>{link.account?.display_name || 'TradingView user'}</span>
                    <span className="edith-subtitle">· linked {fmtTime(link.account?.linked_at)}</span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="edith-btn edith-btn-sm edith-btn-ghost"
                      onClick={() => setShowSignIn(true)}
                    >
                      Open chart
                    </button>
                    <button
                      type="button"
                      className="edith-btn edith-btn-sm edith-btn-ghost text-rose-300"
                      onClick={() => void handleUnlink()}
                      disabled={savingAccount}
                    >
                      Unlink
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="edith-btn edith-btn-sm flex items-center gap-1.5"
                    onClick={() => setShowSignIn(true)}
                  >
                    <LogIn size={14} />
                    Sign in with TradingView
                  </button>
                  <span className="edith-subtitle">
                    Opens embedded chart — sign in on the widget, then confirm below.
                  </span>
                </div>
              )}
            </div>

            <div className="rounded border border-cyan-500/20 bg-cyan-500/5 p-3 space-y-2">
              <div className="edith-label uppercase tracking-wider">Cursor editor tab</div>
              <p className="edith-subtitle leading-relaxed">
                <strong className="text-cyan-300/80 font-normal">Full site (sign in):</strong> Terminal → Run Task →{' '}
                <code className="edith-code">Jarvis: TradingView full site (login)</code>, then sign in on
                tradingview.com in that tab. Jarvis never stores your TV password.
              </p>
              <p className="edith-subtitle leading-relaxed">
                <strong className="text-cyan-300/80 font-normal">Embed chart:</strong> Run Task →{' '}
                <code className="edith-code">Jarvis: Open TradingView in Cursor tab</code>, or paste into{' '}
                <strong className="text-cyan-300/80 font-normal">Simple Browser: Show</strong>.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="edith-btn edith-btn-sm inline-flex items-center gap-1.5"
                  onClick={() => void handleCopy('login')}
                  title="Copy https://www.tradingview.com/ for Simple Browser"
                >
                  {copied === 'login' ? <Check size={14} /> : <LogIn size={14} />}
                  Copy full site (login)
                </button>
                <button
                  type="button"
                  className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1.5"
                  onClick={() => void handleCopy('fullsite')}
                  title="Copy full TV chart URL for Simple Browser"
                >
                  {copied === 'fullsite' ? <Check size={14} /> : <ExternalLink size={14} />}
                  Copy full chart URL
                </button>
                <Link
                  to={`/tradingview?symbol=${encodeURIComponent(chartSymbol)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1.5"
                >
                  <Monitor size={14} />
                  Jarvis embed page
                </Link>
                <button
                  type="button"
                  className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1.5"
                  onClick={() => void handleCopy('cursor')}
                  title="Copy URL for Cursor Simple Browser"
                >
                  {copied === 'cursor' ? <Check size={14} /> : <Copy size={14} />}
                  Copy embed URL
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <span className={`edith-automation-badge ${link.tunnel_configured ? 'active' : ''}`}>
                <Radio size={12} />
                Tunnel {link.tunnel_configured ? 'active' : 'local only'}
              </span>
              <span className="edith-automation-badge">
                Alerts (7d): {link.recent_alert_count}
              </span>
              {link.auto_execute && (
                <span className="edith-automation-badge active">Auto-execute ON</span>
              )}
            </div>

            <div>
              <div className="edith-label uppercase tracking-wider mb-1">Webhook URL</div>
              <div className="flex gap-2 items-start">
                <code className="edith-code flex-1 break-all text-[11px]">{link.webhook_url}</code>
                <button
                  type="button"
                  className="edith-btn edith-btn-sm edith-btn-ghost shrink-0"
                  onClick={() => void handleCopy('url')}
                  title="Copy webhook URL"
                >
                  {copied === 'url' ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
              {!link.tunnel_configured && (
                <p className="edith-subtitle mt-1.5">
                  Start a public tunnel:{' '}
                  <code className="edith-code">scripts\start-tradingview-tunnel.ps1</code>
                  {' '}or set{' '}
                  <code className="edith-code">ngrok_domain</code> in{' '}
                  <code className="edith-code">~/.openjarvis/trading.toml</code> under{' '}
                  <code className="edith-code">[tradingview]</code>.
                </p>
              )}
            </div>

            {!compact && (
              <div>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="edith-label uppercase tracking-wider">Alert message (JSON)</div>
                  <button
                    type="button"
                    className="edith-btn edith-btn-sm edith-btn-ghost"
                    onClick={() => void handleCopy('json')}
                  >
                    {copied === 'json' ? <Check size={12} /> : <Copy size={12} />}
                    Copy template
                  </button>
                </div>
                <pre className="edith-code p-2 overflow-x-auto text-[10px] max-h-36">{templateJson}</pre>
                <p className="edith-subtitle mt-1">
                  In TradingView: create alert → Notifications → Webhook URL → paste URL above.
                  Set the alert message to the JSON template (edit symbol/action as needed).
                </p>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 edith-subtitle">
              <span>Last alert: {fmtTime(link.last_alert_at)}</span>
              <a
                href={link.chart_url_template}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-cyan-400 hover:underline"
              >
                Open sample chart
                <ExternalLink size={12} />
              </a>
            </div>

            {!compact && alerts.length > 0 && (
              <div>
                <div className="edith-label uppercase tracking-wider mb-1">Recent alerts</div>
                <ul className="space-y-1 max-h-32 overflow-y-auto">
                  {alerts.slice(0, 8).map((a, idx) => (
                    <li
                      key={`${a.received_at}-${a.tradingview_symbol}-${idx}`}
                      className="flex justify-between gap-2 px-2 py-1 rounded bg-white/5"
                    >
                      <span className="edith-value truncate">{a.tradingview_symbol}</span>
                      <span className="edith-subtitle shrink-0">
                        {a.action?.toUpperCase() || '—'} · {a.trade_status || 'received'}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {loading && !link && (
          <p className="text-xs edith-subtitle">Loading TradingView link…</p>
        )}
      </section>

      {showSignIn && link && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
          role="dialog"
          aria-modal="true"
          aria-labelledby="tv-signin-title"
        >
          <div className="edith-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto p-4 shadow-2xl border border-cyan-500/20">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 id="tv-signin-title" className="text-sm font-semibold edith-value flex items-center gap-2">
                  <LogIn size={16} style={{ color: 'var(--edith-cyan)' }} />
                  Sign in with TradingView
                </h3>
                <p className="edith-subtitle mt-1 max-w-2xl">
                  Use the chart below to sign into TradingView in this browser. Jarvis cannot read your
                  TV password or issue OAuth tokens — this only stores that you completed sign-in here.
                </p>
              </div>
              <button
                type="button"
                className="edith-btn edith-btn-sm edith-btn-ghost shrink-0"
                onClick={() => setShowSignIn(false)}
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>

            <TradingViewChart
              symbol={chartSymbol}
              interval={link.interval || '5'}
              theme={(link.theme as 'light' | 'dark') ?? 'dark'}
              height={420}
            />

            <div className="mt-4 space-y-3">
              <ol className="list-decimal list-inside edith-subtitle space-y-1">
                <li>Click <strong className="font-normal text-white/80">Sign in</strong> on the chart toolbar (top-right).</li>
                <li>Complete login on tradingview.com — your session stays in this browser.</li>
                <li>Optional: enter a display name, then confirm link.</li>
              </ol>

              <div>
                <label htmlFor="tv-display-name" className="edith-label uppercase tracking-wider mb-1 block">
                  Display name (optional)
                </label>
                <input
                  id="tv-display-name"
                  type="text"
                  className="edith-input w-full max-w-sm text-sm"
                  placeholder="Your TradingView username"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  maxLength={120}
                />
              </div>

              {accountError && <p className="text-xs text-rose-400">{accountError}</p>}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="edith-btn edith-btn-sm"
                  onClick={() => void handleConfirmLink()}
                  disabled={savingAccount}
                >
                  {savingAccount ? 'Saving…' : "I've signed in — confirm link"}
                </button>
                <a
                  href="https://www.tradingview.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="edith-btn edith-btn-sm edith-btn-ghost inline-flex items-center gap-1"
                >
                  Open tradingview.com
                  <ExternalLink size={12} />
                </a>
              </div>

              <p className="edith-subtitle text-[10px] leading-relaxed border-t border-white/10 pt-2">
                Broker connections (Alpaca, IBKR, etc.) on TradingView are separate from Jarvis paper
                trading. Jarvis executes paper trades via webhooks, not your broker OAuth on TV.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
