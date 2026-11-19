export interface DashboardStats {
  equity: number;
  profit: number;
  unrealizedPnl: number;
  winRate: number;
  wins: number;
  losses: number;
  breakeven: number;
  openTrades: number;
  closedTrades: number;
  pendingExecutions: number;
  totalTrades: number;
  activeBots: number;
  strategyDisplay?: boolean;
}

export interface OpenTradeRow {
  id: string;
  symbol: string;
  action: string;
  qty: string;
  entryPrice: number;
  entryCostUsd?: number;
  marketValueUsd?: number;
  markPremium?: number;
  unrealized?: string;
  pnl?: number | null;
  note?: string;
}

export interface ClosedTradeRow {
  id: string;
  symbol: string;
  action: string;
  qty: string;
  entryPrice: number;
  exitPrice?: number;
  pnl: number;
  exitReason?: string;
  note?: string;
}

export type PendingExecutionStatus = 'READY' | 'NEAR' | 'WATCH' | 'BLOCKED';

export interface PendingExecution {
  id: string;
  ticker: string;
  direction: SignalDirection;
  score: number;
  convictionPct?: number;
  minScore: number;
  minConviction: number;
  entry: number;
  status: PendingExecutionStatus;
  gapLabel: string;
  note?: string;
}

export interface TimeSeriesPoint {
  label: string;
  value: number;
  volume?: number;
}

export interface VolumeBar {
  label: string;
  volume: number;
}

export interface AllocationSlice {
  name: string;
  value: number;
  color: string;
}

export type SignalDirection = 'LONG' | 'SHORT';

export interface ScannerSignal {
  id: string;
  ticker: string;
  direction: SignalDirection;
  score: number;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  riskReward: number;
  status: string;
}

export type VoicePhase = 'offline' | 'listening' | 'thinking' | 'speaking' | 'idle';

export interface SystemStatusItem {
  label: string;
  status: 'online' | 'degraded' | 'offline';
  detail?: string;
}

export interface DashboardData {
  stats: DashboardStats;
  profitSeries: TimeSeriesPoint[];
  marketOverview: TimeSeriesPoint[];
  equityCurve: TimeSeriesPoint[];
  strategyPerformance: TimeSeriesPoint[];
  strategyAlphaIndex?: number;
  volumeAnalysis: VolumeBar[];
  winRateSeries: TimeSeriesPoint[];
  allocation: AllocationSlice[];
  signals: ScannerSignal[];
  openTrades: OpenTradeRow[];
  closedTrades: ClosedTradeRow[];
  pendingExecutions: PendingExecution[];
  aiStatus: 'online' | 'processing' | 'standby';
  aiLoad: number;
  systemStatus: SystemStatusItem[];
  lastUpdated: number;
}
