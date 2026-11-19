import { useCallback, useEffect, useState } from 'react';

import {

  checkHealth,

  fetchSpeechHealth,

  fetchTradingAutoStatus,

  fetchTradingLedgerTrades,

  fetchTradingPnl,

  fetchTradingPositions,

  fetchTradingScoutFeed,

  fetchTradingScoutStatus,

  fetchTradingStrategyPerformance,

  fetchTradingStatus,

  type MarketScoutSetup,

  type TradingAutoStatus,

} from '../lib/api';

import { createSampleDashboardData } from '../lib/dashboard/sampleData';

import type {

  ClosedTradeRow,

  DashboardData,

  OpenTradeRow,

  PendingExecution,

  PendingExecutionStatus,

  ScannerSignal,

  TimeSeriesPoint,

} from '../lib/dashboard/types';

import { useAppStore } from '../lib/store';



function parseSpot(spotFmt?: string): number | null {

  if (!spotFmt) return null;

  const n = Number(String(spotFmt).replace(/[^0-9.-]/g, ''));

  return Number.isFinite(n) ? n : null;

}



function confidencePct(setup: MarketScoutSetup): number {

  const raw = setup.signal_score ?? setup.confidence;

  if (raw == null) return 0;

  return Math.round((raw <= 1 ? raw * 100 : raw) * 10) / 10;

}



function setupToSignal(setup: MarketScoutSetup, index: number): ScannerSignal {

  const entry = parseSpot(setup.spot_fmt) ?? 100;

  const isLong =

    setup.direction?.toUpperCase().includes('LONG') || setup.direction?.toUpperCase() === 'BUY';

  const direction = isLong ? 'LONG' : 'SHORT';

  const score = confidencePct(setup);

  const stopPct = 0.03;

  const targetPct = 0.06;

  const stopLoss = isLong ? entry * (1 - stopPct) : entry * (1 + stopPct);

  const takeProfit = isLong ? entry * (1 + targetPct) : entry * (1 - targetPct);

  const risk = Math.abs(entry - stopLoss);

  const reward = Math.abs(takeProfit - entry);

  const riskReward = risk > 0 ? Math.round((reward / risk) * 10) / 10 : 2;



  return {

    id: `${setup.symbol}-${setup.detected_at ?? index}`,

    ticker: setup.symbol,

    direction,

    score,

    entry: Math.round(entry * 100) / 100,

    stopLoss: Math.round(stopLoss * 100) / 100,

    takeProfit: Math.round(takeProfit * 100) / 100,

    riskReward,

    status: score >= 80 ? 'ACTIVE' : score >= 65 ? 'WATCH' : 'PENDING',

  };

}



function buildPendingExecution(

  setup: MarketScoutSetup,

  index: number,

  auto: TradingAutoStatus | null,

): PendingExecution {

  const minScore = auto?.scout_min_confidence_pct ?? 85;

  const minConviction = 78;

  const score = confidencePct(setup);

  const convictionPct = setup.conviction_pct ?? undefined;

  const entry = parseSpot(setup.spot_fmt) ?? 0;

  const isLong =

    setup.direction?.toUpperCase().includes('LONG') || setup.direction?.toUpperCase() === 'BUY';

  const direction = isLong ? 'LONG' : 'SHORT';



  let status: PendingExecutionStatus = 'WATCH';

  const scoreOk = score >= minScore;

  const convOk = convictionPct == null ? true : convictionPct >= minConviction;

  const nearScore = score >= minScore - 6;

  const nearConv = convictionPct == null ? false : convictionPct >= minConviction - 6;



  const directionOk = setup.direction_confirmed !== false;

  if (
    directionOk
    && (setup.auto_eligible || (scoreOk && convOk && setup.entry_allowed !== false))
  ) {

    status = 'READY';

  } else if (setup.entry_allowed === false || !directionOk) {

    status = 'BLOCKED';

  } else if ((nearScore && convOk) || (scoreOk && nearConv) || (nearScore && nearConv)) {

    status = 'NEAR';

  }



  const gaps: string[] = [];

  if (!directionOk && setup.confirmation_note) gaps.push(setup.confirmation_note);
  else if (!directionOk) gaps.push('direction not confirmed');

  if (!scoreOk) gaps.push(`score ${score}% < ${minScore}%`);

  if (convictionPct != null && !convOk) gaps.push(`conviction ${convictionPct}% < ${minConviction}%`);

  const gapLabel =

    status === 'READY'

      ? 'Meets auto-buy gates — BUY-SUPERVISOR will execute'

      : status === 'BLOCKED'

        ? 'Entry blocked by risk or position limits'

        : gaps.length

          ? `Needs: ${gaps.join(', ')}`

          : 'Watching gates';



  return {

    id: `pending-${setup.symbol}-${index}`,

    ticker: setup.symbol,

    direction,

    score,

    convictionPct,

    minScore,

    minConviction,

    entry: Math.round(entry * 100) / 100,

    status,

    gapLabel,

    note: setup.label,

  };

}



function buildProfitSeries(pnl: Awaited<ReturnType<typeof fetchTradingPnl>>) {

  const base = pnl.realized_pnl ?? pnl.session_pnl ?? pnl.today_pnl ?? 0;

  const equity = pnl.equity ?? pnl.starting_equity ?? 10000;

  const start = (pnl.starting_equity ?? equity) - base;

  return ['Start', '-4h', '-2h', 'Now'].map((label, i) => ({

    label,

    value: Math.round((start + base * (i / 3)) * 100) / 100,

  }));

}



function resolveWinStats(
  ledger: Awaited<ReturnType<typeof fetchTradingLedgerTrades>> | null,
  pnl: Awaited<ReturnType<typeof fetchTradingPnl>> | null,
  closedRows: ClosedTradeRow[],
  strategyActive = false,
) {
  if (strategyActive) {
    const wins = ledger?.wins ?? pnl?.wins ?? 0;
    const losses = ledger?.losses ?? pnl?.losses ?? 0;
    const decisive = wins + losses;
    return {
      winRate: decisive > 0
        ? Math.round((wins / decisive) * 1000) / 10
        : ledger?.win_rate_pct ?? pnl?.win_rate_pct ?? 0,
      wins,
      losses,
      breakeven: 0,
      decisive,
    };
  }

  let wins = ledger?.wins ?? pnl?.wins ?? 0;
  let losses = ledger?.losses ?? pnl?.losses ?? 0;
  let breakeven = 0;

  if (closedRows.length) {
    wins = closedRows.filter((t) => t.pnl > 0).length;
    losses = closedRows.filter((t) => t.pnl < 0).length;
    breakeven = closedRows.filter((t) => t.pnl === 0).length;
  } else if ((ledger?.closed_count ?? 0) === 0 && (pnl?.closed_trades ?? 0) > 0) {
    wins = pnl?.wins ?? wins;
    losses = pnl?.losses ?? losses;
  }

  const decisive = wins + losses;
  const winRate =
    decisive > 0
      ? Math.round((wins / decisive) * 1000) / 10
      : ledger?.win_rate_pct ?? pnl?.win_rate_pct ?? 0;

  return { winRate, wins, losses, breakeven, decisive };
}

function buildWinRateSeries(closed: ClosedTradeRow[]): TimeSeriesPoint[] {
  if (!closed.length) {
    return [{ label: '—', value: 0 }];
  }

  let wins = 0;
  let losses = 0;
  const points: TimeSeriesPoint[] = [{ label: 'Start', value: 0 }];

  for (const trade of closed) {
    if (trade.pnl > 0) wins += 1;
    else if (trade.pnl < 0) losses += 1;
    const n = wins + losses;
    points.push({
      label: trade.symbol,
      value: n > 0 ? Math.round((wins / n) * 1000) / 10 : 0,
    });
  }

  return points.length > 14 ? points.slice(-14) : points;
}

function buildEquitySeries(equity: number, starting = 10000) {

  const steps = 7;

  return Array.from({ length: steps }, (_, i) => ({

    label: `T${i}`,

    value: Math.round((starting + ((equity - starting) * i) / Math.max(steps - 1, 1)) * 100) / 100,

  }));

}



function mapOpenTrades(
  ledger: Awaited<ReturnType<typeof fetchTradingLedgerTrades>>,
  livePositions?: Awaited<ReturnType<typeof fetchTradingPositions>> | null,
): OpenTradeRow[] {
  const liveBySymbol = new Map(
    (livePositions?.positions ?? []).map((p) => [String(p.symbol || '').toUpperCase(), p]),
  );

  return (ledger.open ?? []).map((t) => {
    const live = liveBySymbol.get(String(t.symbol || '').toUpperCase());
    return {
      id: `open-${t.n}-${t.symbol}`,
      symbol: t.symbol,
      action: t.action,
      qty: t.qty,
      entryPrice: t.price ?? 0,
      entryCostUsd: live?.entry_cost_usd ?? t.entry_cost_usd,
      marketValueUsd: live?.market_value_usd ?? t.market_value_usd,
      markPremium: live?.mark_premium ?? t.mark_premium,
      unrealized: live?.unrealized ?? t.unrealized,
      pnl: live?.unrealized_pnl ?? t.pnl ?? t.unrealized_pnl ?? null,
      note: t.note,
    };
  });
}



function mapClosedTrades(

  ledger: Awaited<ReturnType<typeof fetchTradingLedgerTrades>>,

): ClosedTradeRow[] {

  return (ledger.closed ?? []).map((t) => ({

    id: `closed-${t.n}-${t.symbol}`,

    symbol: t.symbol,

    action: t.action,

    qty: t.qty,

    entryPrice: t.price ?? 0,

    exitPrice: t.exit_price,

    pnl: t.pnl ?? 0,

    exitReason: t.exit_reason,

    note: t.note,

  }));

}



export function useDashboardData() {

  const [data, setData] = useState<DashboardData>(() => createSampleDashboardData());

  const [loading, setLoading] = useState(true);

  const [usingLiveData, setUsingLiveData] = useState(false);

  const isStreaming = useAppStore((s) => s.streamState.isStreaming);



  const refresh = useCallback(async () => {

    const sample = createSampleDashboardData();



    try {

      const [health, speech, pnl, status, scoutFeed, scoutStatus, autoStatus, ledger, positions, strategyPerf] =

        await Promise.all([

          checkHealth().catch(() => false),

          fetchSpeechHealth().catch(() => ({ available: false })),

          fetchTradingPnl().catch(() => null),

          fetchTradingStatus().catch(() => null),

          fetchTradingScoutFeed().catch(() => null),

          fetchTradingScoutStatus().catch(() => null),

          fetchTradingAutoStatus().catch(() => null),

          fetchTradingLedgerTrades().catch(() => null),

          fetchTradingPositions().catch(() => null),

          fetchTradingStrategyPerformance().catch(() => null),

        ]);



      let merged: DashboardData = { ...sample };

      if (strategyPerf?.available && strategyPerf.series?.length) {
        merged.strategyPerformance = strategyPerf.series.map((p) => ({
          label: p.label,
          value: p.value,
        }));
        merged.strategyAlphaIndex = strategyPerf.alpha_index;
      }

      if (pnl?.available || ledger?.available) {

        const strategyActive = Boolean(pnl?.strategy_display?.active || ledger?.strategy_display?.active);

        const starting = ledger?.starting_equity ?? pnl?.starting_equity ?? 10000;

        const equity = ledger?.equity ?? pnl?.equity ?? starting;

        const realized =
          ledger?.ledger_realized_pnl ?? pnl?.realized_pnl ?? 0;

        const unrealized =
          positions?.positions?.reduce(
            (sum, p) => sum + (Number(p.unrealized_pnl) || 0),
            0,
          ) ?? pnl?.unrealized_pnl ?? 0;

        const openCount = ledger?.open_count ?? pnl?.open_positions ?? 0;

        const closedCount =
          ledger?.closed_count ?? pnl?.closed_trades ?? 0;

        const pendingFromFeed = scoutFeed?.setups?.length ?? 0;

        if (ledger?.available) {
          merged.openTrades = mapOpenTrades(ledger, positions);
          merged.closedTrades = mapClosedTrades(ledger);
        }

        const winStats = resolveWinStats(ledger, pnl, merged.closedTrades, strategyActive);

        merged.stats = {

          equity,

          profit: realized,

          unrealizedPnl: unrealized,

          winRate: winStats.winRate,

          wins: winStats.wins,

          losses: winStats.losses,

          breakeven: winStats.breakeven,

          openTrades: openCount,

          closedTrades: closedCount || merged.closedTrades.length,

          pendingExecutions: pendingFromFeed,

          totalTrades: openCount + (closedCount || merged.closedTrades.length),

          activeBots:

            scoutStatus?.scouts?.filter((s) => s.status === 'running').length ??

            scoutStatus?.scouts?.length ??

            0,

          strategyDisplay: strategyActive,

        };

        const charts = pnl?.strategy_charts ?? ledger?.strategy_charts;

        if (strategyActive && charts?.profit_series?.length) {
          merged.profitSeries = charts.profit_series;
          merged.equityCurve = charts.equity_curve?.length
            ? charts.equity_curve
            : buildEquitySeries(equity, starting);
          merged.winRateSeries = charts.win_rate_series?.length
            ? charts.win_rate_series
            : buildWinRateSeries(merged.closedTrades);
        } else {
          merged.profitSeries = pnl ? buildProfitSeries(pnl) : buildEquitySeries(realized + starting, starting);
          merged.equityCurve = buildEquitySeries(equity, starting);
          merged.winRateSeries = buildWinRateSeries(merged.closedTrades);
        }

      }



      if (scoutFeed?.setups?.length) {

        merged.signals = scoutFeed.setups.slice(0, 9).map(setupToSignal);

        merged.pendingExecutions = scoutFeed.setups

          .map((s, i) => buildPendingExecution(s, i, autoStatus))

          .sort((a, b) => {

            const order = { READY: 0, NEAR: 1, WATCH: 2, BLOCKED: 3 };

            return order[a.status] - order[b.status] || b.score - a.score;

          });

        merged.stats = {

          ...merged.stats,

          pendingExecutions: merged.pendingExecutions.filter(

            (p) => p.status === 'READY' || p.status === 'NEAR',

          ).length,

        };

        merged.volumeAnalysis = scoutFeed.setups.slice(0, 8).map((s) => ({

          label: s.symbol,

          volume: Math.round(

            (s.confidence <= 1 ? s.confidence * 10000 : s.confidence * 100) + (s.rsi ?? 50) * 20,

          ),

        }));

        merged.marketOverview = scoutFeed.setups.slice(0, 7).map((s, i) => ({

          label: s.symbol,

          value: parseSpot(s.spot_fmt) ?? 100 + i * 3,

          volume: Math.round(1000 + (s.confidence <= 1 ? s.confidence * 5000 : s.confidence * 50)),

        }));

      } else {

        merged.pendingExecutions = [];

      }



      if (scoutStatus) {

        merged.systemStatus = [

          {

            label: 'Inference',

            status: health ? 'online' : 'offline',

            detail: isStreaming ? 'Generating' : 'Ready',

          },

          {

            label: 'Scout Feed',

            status: scoutStatus.running ? 'online' : 'degraded',

            detail:

              scoutStatus.setup_count != null

                ? `${scoutStatus.setup_count} setups`

                : undefined,

          },

          {

            label: 'Paper Trading',

            status: status?.available ? 'online' : 'degraded',

            detail: status?.session?.mode,

          },

          {

            label: 'Auto Buy',

            status: autoStatus?.enabled && autoStatus?.auto_buy ? 'online' : 'degraded',

            detail: autoStatus

              ? `min ${autoStatus.scout_min_confidence_pct}% confidence`

              : undefined,

          },

          {

            label: 'Speech',

            status: speech.available ? 'online' : 'offline',

            detail: speech.available ? 'STT/TTS' : 'Unavailable',

          },

        ];

      }



      merged.aiStatus = isStreaming ? 'processing' : health ? 'online' : 'standby';

      merged.aiLoad = isStreaming ? 78 : scoutStatus?.running ? 48 : 32;

      merged.lastUpdated = Date.now();



      setData(merged);

      setUsingLiveData(

        Boolean(
          pnl?.available
          || ledger?.available
          || scoutFeed?.setups?.length
          || strategyPerf?.available,
        ),

      );

    } catch {

      setData(sample);

      setUsingLiveData(false);

    } finally {

      setLoading(false);

    }

  }, [isStreaming]);



  useEffect(() => {

    void refresh();

    const interval = window.setInterval(() => void refresh(), 5000);

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void refresh();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };

  }, [refresh]);



  return { data, loading, usingLiveData, refresh };

}


