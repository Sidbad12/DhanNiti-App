// DhanNiti — Phase C API Client
// All fetch() calls go through here. No fetch() scattered in components.

import type {
  PortfolioReport,
  CandlestickResponse,
  VixResponse,
  NewsResponse,
  RebalanceCostResponse,
  HoldingsResponse,
  GapResponse,
} from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function fetchCurrentPortfolio(): Promise<{
  report: PortfolioReport | null;
  isUsingFallback: boolean;
  error?: string;
}> {
  // Primary: FastAPI server (V2 endpoint)
  try {
    const res = await fetch(
      `${BASE}/v2/portfolio/current`,
      { cache: "no-store", signal: AbortSignal.timeout(15000) } // 15s timeout for cold start
    );
    if (res.ok) {
      const data = await res.json();
      return { report: data, isUsingFallback: false };
    }
  } catch (err) {
    // API unreachable (server off, tunnel down, timeout) — fall through to Supabase
    console.warn("FastAPI unreachable — falling back to Supabase direct read", err);
  }

  // Fallback: read advisory_reports directly from Supabase (filtered by version v2 in-memory)
  const { createClient } = await import("@supabase/supabase-js");
  
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    return { report: null, isUsingFallback: false, error: "Supabase environment variables are not configured in frontend." };
  }

  const supabase = createClient(supabaseUrl, supabaseAnonKey);

  const { data, error } = await supabase
    .from("advisory_reports")
    .select("full_report, report_date")
    .order("report_date", { ascending: false })
    .limit(20);

  if (error || !data || data.length === 0) {
    return { report: null, isUsingFallback: false, error: "No V2 portfolio data available. Run the pipeline first." };
  }

  const v2ReportRow = data.find((row) => {
    const reportObj = typeof row.full_report === "string"
      ? JSON.parse(row.full_report)
      : row.full_report;
    return reportObj?.source === "v2_sac_recommend" || reportObj?.model_version === "v2";
  });

  if (!v2ReportRow) {
    return { report: null, isUsingFallback: false, error: "No V2 portfolio data available. Run the pipeline first." };
  }

  const report = (typeof v2ReportRow.full_report === "string"
    ? JSON.parse(v2ReportRow.full_report)
    : v2ReportRow.full_report) as PortfolioReport;

  return { report, isUsingFallback: true };
}

export async function fetchRecommendation(
  useGroq = true,
  persist = true,
  tickers?: string[],
  startDate?: string,
  forceRetrain = true,
  asOf?: string
): Promise<PortfolioReport> {
  let url = `${BASE}/v2/portfolio/recommend?use_groq=${useGroq}&persist=${persist}&force_retrain=${forceRetrain}`;
  if (tickers && tickers.length > 0) {
    url += `&tickers=${encodeURIComponent(tickers.join(","))}`;
  }
  if (startDate) {
    url += `&start_date=${encodeURIComponent(startDate)}`;
  }
  if (asOf) {
    url += `&as_of=${encodeURIComponent(asOf)}`;
  }
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Recommend failed: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function fetchCandlesticks(ticker: string): Promise<CandlestickResponse> {
  const res = await fetch(`${BASE}/data/candlesticks/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Candlesticks fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchVix(): Promise<VixResponse> {
  const res = await fetch(`${BASE}/data/vix`, { cache: "no-store" });
  if (!res.ok) throw new Error(`VIX fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchNews(ticker: string): Promise<NewsResponse> {
  const res = await fetch(`${BASE}/data/news/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`News fetch failed: ${res.status}`);
  return res.json();
}

export async function simulateRebalanceCost(
  currentWeights: Record<string, number>,
  targetWeights: Record<string, number>,
  portfolioValue: number
): Promise<RebalanceCostResponse> {
  const res = await fetch(`${BASE}/simulate/rebalance-cost`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_weights: currentWeights,
      target_weights: targetWeights,
      portfolio_value: portfolioValue,
    }),
  });
  if (!res.ok) throw new Error(`Rebalance simulation failed: ${res.status}`);
  return res.json();
}

export function getWsUrl(): string {
  return BASE.replace(/^http/, "ws") + "/ws";
}

export async function fetchHoldings(): Promise<HoldingsResponse> {
  const res = await fetch(`${BASE}/portfolio/holdings`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch holdings");
  return res.json();
}

export async function fetchHoldingsGap(): Promise<GapResponse> {
  const res = await fetch(`${BASE}/portfolio/holdings/gap`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch gap analysis");
  return res.json();
}

export async function addHolding(data: {
  ticker: string;
  quantity: number;
  buy_price: number;
  buy_date: string;
  notes?: string;
}): Promise<any> {
  const res = await fetch(`${BASE}/portfolio/holdings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to add holding");
  return res.json();
}

export async function deleteHolding(id: string): Promise<any> {
  const res = await fetch(`${BASE}/portfolio/holdings/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete holding");
  return res.json();
}
