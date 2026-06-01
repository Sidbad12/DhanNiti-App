// DhanNiti — Demo Phase C API Client
// Used purely by the Vercel preview/demo version.
// Uses client-side localStorage for holdings and Next.js API routes for market data.

import type {
  PortfolioReport,
  CandlestickResponse,
  VixResponse,
  NewsResponse,
  RebalanceCostResponse,
  HoldingsResponse,
  GapResponse,
  Holding,
  GapItem,
} from "@/types/api";

const BASE = "/api/demo";

// Helper to get holdings from local storage
const getLocalHoldings = (): Holding[] => {
  if (typeof window === "undefined") return [];
  const stored = localStorage.getItem("dhanniti_demo_holdings");
  if (!stored) {
    // Seed with some initial mock holdings for the demo
    const initial: Holding[] = [
      {
        id: "demo-1",
        ticker: "RELIANCE.NS",
        quantity: 50,
        buy_price: 2450.0,
        buy_date: "2025-10-15",
        notes: "Initial investment in energy/retail",
        current_price: 2510.5,
        invested_value: 122500.0,
        current_value: 125525.0,
        unrealised_pnl: 3025.0,
        unrealised_pnl_pct: 2.47,
      },
      {
        id: "demo-2",
        ticker: "TCS.NS",
        quantity: 30,
        buy_price: 3400.0,
        buy_date: "2025-11-20",
        notes: "Defensive IT play",
        current_price: 3380.0,
        invested_value: 102000.0,
        current_value: 101400.0,
        unrealised_pnl: -600.0,
        unrealised_pnl_pct: -0.59,
      },
    ];
    localStorage.setItem("dhanniti_demo_holdings", JSON.stringify(initial));
    return initial;
  }
  return JSON.parse(stored);
};

const saveLocalHoldings = (holdings: Holding[]) => {
  localStorage.setItem("dhanniti_demo_holdings", JSON.stringify(holdings));
};

export async function fetchCurrentPortfolio(): Promise<{
  report: PortfolioReport | null;
  isUsingFallback: boolean;
  error?: string;
}> {
  // Read advisory_reports directly from Supabase
  try {
    const { createClient } = await import("@supabase/supabase-js");
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (supabaseUrl && supabaseAnonKey) {
      const supabase = createClient(supabaseUrl, supabaseAnonKey);
      const { data, error } = await supabase
        .from("advisory_reports")
        .select("full_report, report_date")
        .order("report_date", { ascending: false })
        .limit(20);

      if (!error && data && data.length > 0) {
        const v2ReportRow = data.find((row) => {
          const reportObj = typeof row.full_report === "string"
            ? JSON.parse(row.full_report)
            : row.full_report;
          return reportObj?.source === "v2_sac_recommend" || reportObj?.model_version === "v2";
        });

        if (v2ReportRow) {
          const report = (typeof v2ReportRow.full_report === "string"
            ? JSON.parse(v2ReportRow.full_report)
            : v2ReportRow.full_report) as PortfolioReport;
          return { report, isUsingFallback: false };
        }
      }
    }
  } catch (err) {
    console.warn("Direct Supabase fetch failed in demo mode, loading default mock report", err);
  }

  // Final fallback: Return a beautifully detailed Mock Portfolio Report
  const mockReport: PortfolioReport = {
    date: new Date().toISOString().split("T")[0],
    as_of: new Date().toISOString(),
    regime: "bull_trending",
    regime_probs: { bull_trending: 0.72, range_bound: 0.18, bear_trending: 0.1 },
    regime_commentary: "Nifty 50 exhibits strong positive momentum above key moving averages. Institutional inflows (FII) remain positive, and VIX is stable under 14.5, favoring strategic equity long bias.",
    source: "v2_sac_recommend",
    tickers: ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "ITC.NS", "LT.NS", "BHARTIARTL.NS"],
    allocations: {
      "RELIANCE.NS": 0.15,
      "TCS.NS": 0.08,
      "INFY.NS": 0.07,
      "HDFCBANK.NS": 0.18,
      "ICICIBANK.NS": 0.12,
      "SBIN.NS": 0.08,
      "TATAMOTORS.NS": 0.10,
      "ITC.NS": 0.07,
      "LT.NS": 0.08,
      "BHARTIARTL.NS": 0.07,
    },
    ppo_allocations: {
      "RELIANCE.NS": 0.14,
      "TCS.NS": 0.08,
      "INFY.NS": 0.06,
      "HDFCBANK.NS": 0.16,
      "ICICIBANK.NS": 0.12,
      "SBIN.NS": 0.09,
      "TATAMOTORS.NS": 0.08,
      "ITC.NS": 0.08,
      "LT.NS": 0.10,
      "BHARTIARTL.NS": 0.09,
    },
    sac_allocations: {
      "RELIANCE.NS": 0.15,
      "TCS.NS": 0.08,
      "INFY.NS": 0.07,
      "HDFCBANK.NS": 0.18,
      "ICICIBANK.NS": 0.12,
      "SBIN.NS": 0.08,
      "TATAMOTORS.NS": 0.10,
      "ITC.NS": 0.07,
      "LT.NS": 0.08,
      "BHARTIARTL.NS": 0.07,
    },
    expected_return: 0.185,
    llm_confidence: 0.88,
    reasoning: "The SAC reinforcement learning model suggests overweighting high-beta quality cyclicals (Tata Motors, Reliance, ICICI Bank) during this bullish regime expansion. HDFC Bank is weighted highly as a core portfolio anchor. Alt-data sentiment shows extremely strong positive social media traction for EV commercialization and infrastructure spending, supporting Tata Motors and Larsen & Toubro.",
    risk_flags: ["Concentration risk in Financial services (30%)", "Global IT spend moderation macro headwinds"],
    stock_breakdowns: [
      { ticker: "RELIANCE.NS", final_weight: 0.15, xgb_signal: "bullish", xgb_confidence: 0.81, note: "Jamnagar green energy complex starting pilot production next quarter." },
      { ticker: "HDFCBANK.NS", final_weight: 0.18, xgb_signal: "neutral", xgb_confidence: 0.65, note: "Core anchor. NIM stability is projected over next 2 quarters." },
      { ticker: "TATAMOTORS.NS", final_weight: 0.10, xgb_signal: "bullish", xgb_confidence: 0.89, note: "JLR volume recovery and EV market leadership support growth." },
      { ticker: "LT.NS", final_weight: 0.08, xgb_signal: "bullish", xgb_confidence: 0.76, note: "Record infrastructure order book from domestic public Capex." },
      { ticker: "TCS.NS", final_weight: 0.08, xgb_signal: "neutral", xgb_confidence: 0.58, note: "Strong cash conversion and cloud migrations deal momentum." },
    ],
    memory_citations: [
      { date: "2024-06-12", similarity: "84.2%", outcome: "Similar regime transition led to 4.2% outperformance over Nifty over 30 days." },
    ],
    weight_sum: 1.0,
    generated_at: new Date().toISOString(),
    model_version: "v2",
  };

  return { report: mockReport, isUsingFallback: true };
}

export async function fetchRecommendation(
  useGroq = true,
  persist = true,
  tickers?: string[],
  startDate?: string,
  forceRetrain = true,
  asOf?: string
): Promise<PortfolioReport> {
  // Simulate a delay for the agent pipeline
  await new Promise((resolve) => setTimeout(resolve, 3000));

  const selectedTickers = tickers && tickers.length > 0
    ? tickers
    : ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"];

  // Create customized weights dynamically for the demo
  const equalWeight = 1.0 / selectedTickers.length;
  const allocations: Record<string, number> = {};
  const ppo_allocations: Record<string, number> = {};
  const stock_breakdowns: any[] = [];

  selectedTickers.forEach((t) => {
    allocations[t] = equalWeight;
    ppo_allocations[t] = equalWeight;
    stock_breakdowns.push({
      ticker: t,
      final_weight: equalWeight,
      xgb_signal: "bullish",
      xgb_confidence: 0.75,
      note: "XGBoost trend classifier indicates strong relative strength support.",
    });
  });

  return {
    date: new Date().toISOString().split("T")[0],
    as_of: new Date().toISOString(),
    regime: "bull_trending",
    regime_probs: { bull_trending: 0.8, range_bound: 0.2 },
    regime_commentary: "Custom optimization run complete. The model adapted successfully to the custom stock list.",
    source: "v2_sac_recommend",
    tickers: selectedTickers,
    allocations,
    ppo_allocations,
    expected_return: 0.162,
    llm_confidence: 0.82,
    reasoning: `Successfully rebalanced portfolio across your selected stock universe. Equalized allocations of ${(equalWeight * 100).toFixed(1)}% are recommended to mitigate idiosyncratic stock risk under current high momentum.`,
    risk_flags: [],
    stock_breakdowns,
    memory_citations: [],
    weight_sum: 1.0,
    generated_at: new Date().toISOString(),
    model_version: "v2",
  };
}

export async function fetchCandlesticks(ticker: string): Promise<CandlestickResponse> {
  const res = await fetch(`${BASE}/data/candlesticks/${ticker}`);
  if (!res.ok) throw new Error(`Candlesticks fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchVix(): Promise<VixResponse> {
  const res = await fetch(`${BASE}/data/vix`);
  if (!res.ok) throw new Error(`VIX fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchNews(ticker: string): Promise<NewsResponse> {
  const res = await fetch(`${BASE}/data/news/${ticker}`);
  if (!res.ok) throw new Error(`News fetch failed: ${res.status}`);
  return res.json();
}

export async function simulateRebalanceCost(
  currentWeights: Record<string, number>,
  targetWeights: Record<string, number>,
  portfolioValue: number
): Promise<RebalanceCostResponse> {
  // Rebalance cost math calculated directly on the client for Vercel
  let totalTurnover = 0;
  const allTickers = new Set([...Object.keys(currentWeights), ...Object.keys(targetWeights)]);

  allTickers.forEach((ticker) => {
    const cur = currentWeights[ticker] || 0;
    const tgt = targetWeights[ticker] || 0;
    totalTurnover += Math.abs(cur - tgt);
  });

  // Turn over value is in INR (total turnover weight / 2 * portfolio value)
  const turnoverVal = (totalTurnover / 2) * portfolioValue;
  // Estimate transaction fees: brokerage (0.05%) + STT/GST/Stamp duty (0.15%) = 0.2%
  const estimatedCost = turnoverVal * 0.002;

  return {
    estimated_cost_inr: Math.max(20, estimatedCost), // Min 20 INR
    portfolio_value: portfolioValue,
  };
}

export function getWsUrl(): string {
  // Return dummy URL or empty string since we mock WebSockets in the demo
  return "";
}

// ── LocalStorage Holdings Database ───────────────────────────

export async function fetchHoldings(): Promise<HoldingsResponse> {
  const list = getLocalHoldings();
  let totalInvested = 0;
  let totalCurrentValue = 0;

  list.forEach((h) => {
    totalInvested += h.invested_value;
    totalCurrentValue += h.current_value || h.invested_value;
  });

  const totalUnrealisedPnl = totalCurrentValue - totalInvested;
  const totalUnrealisedPnlPct = totalInvested > 0 ? (totalUnrealisedPnl / totalInvested) * 100 : 0;

  return {
    holdings: list,
    summary: {
      total_invested: totalInvested,
      total_current_value: totalCurrentValue,
      total_unrealised_pnl: totalUnrealisedPnl,
      total_unrealised_pnl_pct: totalUnrealisedPnlPct,
    },
  };
}

export async function fetchHoldingsGap(): Promise<GapResponse> {
  const list = getLocalHoldings();
  const reportRes = await fetchCurrentPortfolio();
  const targetAllocations = reportRes.report?.allocations || {};

  let totalCurrentValue = 0;
  list.forEach((h) => {
    totalCurrentValue += h.current_value || h.invested_value;
  });

  // If no portfolio holdings, default portfolio value to 10 Lakhs INR
  const portfolioValue = totalCurrentValue > 0 ? totalCurrentValue : 1000000.0;

  const gap_analysis: GapItem[] = [];
  const tickersInTarget = Object.keys(targetAllocations);
  const tickersInHoldings = list.map((h) => h.ticker);
  const allSymbols = Array.from(new Set([...tickersInTarget, ...tickersInHoldings]));

  allSymbols.forEach((symbol) => {
    const holdingItem = list.find((h) => h.ticker === symbol);
    const heldWeight = totalCurrentValue > 0 && holdingItem ? (holdingItem.current_value || 0) / totalCurrentValue : 0;
    const ppoWeight = targetAllocations[symbol] || 0;
    const gap = ppoWeight - heldWeight;
    const deltaInr = gap * portfolioValue;

    let action: "buy" | "sell" | "hold" = "hold";
    if (gap > 0.01) {
      action = "buy";
    } else if (gap < -0.01) {
      action = "sell";
    }

    gap_analysis.push({
      ticker: symbol,
      held_weight: heldWeight,
      ppo_weight: ppoWeight,
      gap,
      action,
      delta_inr: deltaInr,
    });
  });

  return {
    gap_analysis,
    portfolio_value: portfolioValue,
    as_of: new Date().toISOString(),
  };
}

export async function addHolding(data: {
  ticker: string;
  quantity: number;
  buy_price: number;
  buy_date: string;
  notes?: string;
}): Promise<any> {
  const list = getLocalHoldings();
  const investedVal = data.quantity * data.buy_price;

  const newHolding: Holding = {
    id: "demo-" + Math.random().toString(36).substr(2, 9),
    ticker: data.ticker,
    quantity: data.quantity,
    buy_price: data.buy_price,
    buy_date: data.buy_date,
    notes: data.notes,
    current_price: data.buy_price * 1.02, // Mock 2% gain initially
    invested_value: investedVal,
    current_value: investedVal * 1.02,
    unrealised_pnl: investedVal * 0.02,
    unrealised_pnl_pct: 2.0,
  };

  list.push(newHolding);
  saveLocalHoldings(list);
  return { success: true, holding: newHolding };
}

export async function deleteHolding(id: string): Promise<any> {
  let list = getLocalHoldings();
  list = list.filter((h) => h.id !== id);
  saveLocalHoldings(list);
  return { success: true };
}
