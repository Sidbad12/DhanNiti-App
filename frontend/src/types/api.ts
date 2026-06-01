// DhanNiti — Phase C API Types
// Matches the real FastAPI response shapes from Phase B

// GET /portfolio/current  and  /portfolio/recommend
export interface PortfolioReport {
  date: string;
  as_of: string;
  regime: string;                          // "high_volatility" | "bull_trending" | "bear_trending" | "range_bound"
  regime_probs: Record<string, number>;    // { bull_trending: 0.1, high_volatility: 0.7 }
  regime_commentary: string;               // Groq's regime read
  source: string;                          // "v1_ppo_groq" | "v1_ppo_recommend"
  tickers: string[];
  allocations: Record<string, number>;     // PPO/SAC weights
  ppo_allocations: Record<string, number>; // canonical PPO weights
  sac_allocations?: Record<string, number>; // canonical V2 SAC weights
  expected_return: number;                 // e.g. 0.17
  llm_confidence: number;                  // 0.0–1.0
  reasoning: string;                       // Groq prose narrative
  risk_flags: string[];
  stock_breakdowns: StockBreakdown[];
  memory_citations: MemoryCitation[];
  weight_sum: number;
  generated_at: string;                    // ISO timestamp
  model_version: string;                   // "v1" or "v2"
  start_date?: string;
  report_date?: string;
}

export interface StockBreakdown {
  ticker: string;
  final_weight: number;                    // PPO weight
  xgb_signal: string;                      // "bullish" | "bearish" | "neutral"
  xgb_confidence: number;
  note: string;                            // Groq's per-stock rationale
}

export interface MemoryCitation {
  date: string;
  similarity: string;
  outcome: string;
}

// GET /data/candlesticks/{ticker}
export interface CandlestickResponse {
  ticker: string;
  data: OHLCV[];
}

export interface OHLCV {
  time: string;   // "YYYY-MM-DD"
  open: number;
  high: number;
  low: number;
  close: number;
}

// GET /data/vix
export interface VixResponse {
  vix: number;
  status: "calm" | "caution" | "fear";
}

// GET /data/news/{ticker}
export interface NewsResponse {
  ticker: string;
  headlines: string[];
  sentiment: {
    composite: number;
    positive: number;
    negative: number;
    neutral: number;
  };
}

// POST /simulate/rebalance-cost
export interface RebalanceCostRequest {
  current_weights: Record<string, number>;
  target_weights: Record<string, number>;
  portfolio_value: number;
}

export interface RebalanceCostResponse {
  estimated_cost_inr: number;
  portfolio_value: number;
}

// WebSocket progress message
export interface WsProgressMessage {
  type: "progress" | "system";
  node?: string;
  status?: "running" | "completed" | "error";
  message?: string;
}

export interface Holding {
  id: string;
  ticker: string;
  quantity: number;
  buy_price: number;
  buy_date: string;
  notes?: string;
  current_price: number | null;
  invested_value: number;
  current_value: number | null;
  unrealised_pnl: number | null;
  unrealised_pnl_pct: number | null;
}

export interface HoldingsSummary {
  total_invested: number;
  total_current_value: number;
  total_unrealised_pnl: number;
  total_unrealised_pnl_pct: number;
}

export interface HoldingsResponse {
  holdings: Holding[];
  summary: HoldingsSummary;
}

export interface GapItem {
  ticker: string;
  held_weight: number;
  ppo_weight: number;
  gap: number;
  action: "buy" | "sell" | "hold";
  delta_inr: number;
}

export interface GapResponse {
  gap_analysis: GapItem[];
  portfolio_value: number;
  as_of: string;
}
