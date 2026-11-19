import { Link } from 'react-router';
import { Crosshair, RefreshCw } from 'lucide-react';
import { AiCorePanel } from '../components/Dashboard/AiCorePanel';
import { AssetAllocationChart } from '../components/Dashboard/AssetAllocationChart';
import { DashboardLayout } from '../components/Dashboard/DashboardLayout';
import { EquityCurveChart } from '../components/Dashboard/EquityCurveChart';
import { MarketOverviewChart } from '../components/Dashboard/MarketOverviewChart';
import { ProfitChart } from '../components/Dashboard/ProfitChart';
import { ScannerSignalsPanel } from '../components/Dashboard/ScannerSignalsPanel';
import { StatsPanel } from '../components/Dashboard/StatsPanel';
import { TradesOverviewPanel } from '../components/Dashboard/TradesOverviewPanel';
import { StrategyPerformanceChart } from '../components/Dashboard/StrategyPerformanceChart';
import { SystemStatusPanel } from '../components/Dashboard/SystemStatusPanel';
import { VoiceStatusPanel } from '../components/Dashboard/VoiceStatusPanel';
import { VolumeAnalysisChart } from '../components/Dashboard/VolumeAnalysisChart';
import { WinRateChart } from '../components/Dashboard/WinRateChart';
import { useDashboardData } from '../hooks/useDashboardData';
import '../styles/dashboard.css';

export function DashboardPage() {
  const { data, loading, usingLiveData, refresh } = useDashboardData();

  return (
    <DashboardLayout
      header={
        <header className="at-hero px-5 py-5 md:px-7 md:py-6">
          <div className="at-hero-beam" aria-hidden />
          <div className="relative z-[1] flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="at-display text-[10px] text-[var(--at-lime)]">
                Paper · On-device · No cloud book
              </p>
              <h1 className="at-display mt-2 text-2xl font-semibold text-[var(--at-ink)] md:text-[2rem]">
                Alpaca Terminal
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--at-muted)]">
                {data.stats.strategyDisplay
                  ? 'Strategy book — replay baseline + live paper fills. Refreshes every 5s.'
                  : 'All-time paper book — equity and trade history persist across restarts.'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`at-chip ${usingLiveData ? 'at-chip-live' : 'at-chip-sample'}`}>
                {usingLiveData ? 'Live feed' : 'Sample data'}
              </span>
              <Link to="/mnq-eval" className="at-btn no-underline">
                <Crosshair size={12} />
                MNQ Eval
              </Link>
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loading}
                className="at-btn"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                Sync
              </button>
            </div>
          </div>
        </header>
      }
      topLeft={<AiCorePanel status={data.aiStatus} load={data.aiLoad} />}
      topCenter={<StatsPanel stats={data.stats} />}
      topRight={<ProfitChart data={data.profitSeries} />}
      middleLeft={<MarketOverviewChart data={data.marketOverview} />}
      middleCenter={<EquityCurveChart data={data.equityCurve} equity={data.stats.equity} />}
      middleRight={
        <StrategyPerformanceChart
          data={data.strategyPerformance}
          alphaIndex={data.strategyAlphaIndex}
        />
      }
      bottomLeft={<VolumeAnalysisChart data={data.volumeAnalysis} />}
      bottomCenter={
        <WinRateChart
          data={data.winRateSeries}
          wins={data.stats.wins}
          losses={data.stats.losses}
          breakeven={data.stats.breakeven}
        />
      }
      bottomRight={<AssetAllocationChart data={data.allocation} />}
      trades={
        <TradesOverviewPanel
          openTrades={data.openTrades}
          closedTrades={data.closedTrades}
          pendingExecutions={data.pendingExecutions}
          strategyDisplay={data.stats.strategyDisplay}
        />
      }
      scanner={<ScannerSignalsPanel signals={data.signals} />}
      footer={[
        <VoiceStatusPanel key="voice" />,
        <SystemStatusPanel key="system" items={data.systemStatus} lastUpdated={data.lastUpdated} />,
      ]}
    />
  );
}
