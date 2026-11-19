import type { DashboardData } from './types';

const HOURS = ['00', '04', '08', '12', '16', '20', '24'];

function series(base: number, variance: number): { label: string; value: number; volume?: number }[] {
  return HOURS.map((label, i) => ({
    label: `${label}h`,
    value: Math.round((base + Math.sin(i * 0.9) * variance + i * (variance / 8)) * 100) / 100,
    volume: Math.round(1200 + Math.cos(i * 1.1) * 400 + i * 80),
  }));
}

export function createSampleDashboardData(): DashboardData {
  return {
    stats: {
      equity: 1000,
      profit: 0,
      unrealizedPnl: 0,
      winRate: 0,
      wins: 0,
      losses: 0,
      breakeven: 0,
      openTrades: 0,
      closedTrades: 0,
      pendingExecutions: 0,
      totalTrades: 0,
      activeBots: 0,
    },
    openTrades: [
      { id: 'o1', symbol: 'BTC-USD', action: 'BUY', qty: '2x BUY CALL', entryPrice: 98500, unrealized: '+$124.50', note: 'bull_flag' },
      { id: 'o2', symbol: 'ETH-USD', action: 'BUY', qty: '2x BUY CALL', entryPrice: 3420, unrealized: '+$48.20', note: 'scout feed' },
      { id: 'o3', symbol: 'SOL-USD', action: 'BUY', qty: '2x BUY PUT', entryPrice: 142.5, unrealized: '-$12.10', note: 'double_top' },
    ],
    closedTrades: [
      { id: 'c1', symbol: 'DOGE-USD', action: 'BUY', qty: '2x BUY CALL', entryPrice: 0.42, exitPrice: 0.48, pnl: 24.5, exitReason: 'take profit', note: 'scout' },
      { id: 'c2', symbol: 'AVAX-USD', action: 'BUY', qty: '2x BUY PUT', entryPrice: 38.2, exitPrice: 36.1, pnl: 18.2, exitReason: 'TP1', note: 'pattern' },
    ],
    pendingExecutions: [
      { id: 'p1', ticker: 'LINK-USD', direction: 'LONG', score: 87, convictionPct: 82, minScore: 85, minConviction: 78, entry: 18.4, status: 'READY', gapLabel: 'Meets auto-buy gates' },
      { id: 'p2', ticker: 'ARB-USD', direction: 'SHORT', score: 81, convictionPct: 74, minScore: 85, minConviction: 78, entry: 1.12, status: 'NEAR', gapLabel: 'Needs +4% score, +4% conviction' },
    ],
    profitSeries: HOURS.map((label, i) => ({
      label: `${label}h`,
      value: Math.round(1200 + i * 420 + Math.sin(i) * 300),
    })),
    marketOverview: series(142.5, 8.2),
    equityCurve: HOURS.map((label) => ({
      label: `${label}h`,
      value: 1000,
    })),
    strategyPerformance: HOURS.map((label, i) => ({
      label: `${label}h`,
      value: Math.round((58 + i * 2.4 + Math.cos(i) * 5) * 10) / 10,
    })),
    volumeAnalysis: ['BTC', 'ETH', 'SOL', 'NVDA', 'AAPL', 'TSLA', 'AMD', 'META'].map((label, i) => ({
      label,
      volume: Math.round(8000 + i * 900 + Math.sin(i) * 2000),
    })),
    winRateSeries: HOURS.map((label, i) => ({
      label: `${label}h`,
      value: Math.round((62 + Math.sin(i * 0.8) * 8 + i * 0.5) * 10) / 10,
    })),
    allocation: [
      { name: 'Crypto', value: 38, color: '#22d3ee' },
      { name: 'Tech', value: 27, color: '#38bdf8' },
      { name: 'Energy', value: 14, color: '#2dd4bf' },
      { name: 'Cash', value: 21, color: '#67e8f9' },
    ],
    signals: [
      {
        id: '1',
        ticker: 'NVDA',
        direction: 'LONG',
        score: 87,
        entry: 892.4,
        stopLoss: 865.2,
        takeProfit: 945.0,
        riskReward: 2.4,
        status: 'ACTIVE',
      },
      {
        id: '2',
        ticker: 'BTCUSD',
        direction: 'LONG',
        score: 79,
        entry: 68420,
        stopLoss: 66800,
        takeProfit: 71200,
        riskReward: 1.8,
        status: 'WATCH',
      },
      {
        id: '3',
        ticker: 'TSLA',
        direction: 'SHORT',
        score: 72,
        entry: 248.6,
        stopLoss: 256.1,
        takeProfit: 232.4,
        riskReward: 2.1,
        status: 'PENDING',
      },
    ],
    aiStatus: 'online',
    aiLoad: 42,
    systemStatus: [
      { label: 'Inference', status: 'online', detail: 'Local LLM' },
      { label: 'Scout Feed', status: 'online', detail: 'Polling' },
      { label: 'Paper Trading', status: 'online' },
      { label: 'Speech', status: 'degraded', detail: 'STT ready' },
    ],
    lastUpdated: Date.now(),
  };
}
