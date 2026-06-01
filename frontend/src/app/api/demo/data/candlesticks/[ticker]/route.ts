import { NextResponse } from "next/server";

export const dynamic = "force-static";

export function generateStaticParams() {
  return [
    { ticker: "RELIANCE.NS" },
    { ticker: "TCS.NS" },
    { ticker: "INFY.NS" },
    { ticker: "HDFCBANK.NS" },
    { ticker: "ICICIBANK.NS" },
    { ticker: "SBIN.NS" },
    { ticker: "TATAMOTORS.NS" },
    { ticker: "ITC.NS" },
    { ticker: "LT.NS" },
    { ticker: "BHARTIARTL.NS" }
  ];
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  // Await the params since Next.js App Router dynamic params are asynchronous in modern Next versions
  const resolvedParams = await params;
  const ticker = resolvedParams.ticker;

  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=1y`,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
      }
    );

    if (!res.ok) {
      throw new Error(`Yahoo Finance responded with status ${res.status}`);
    }

    const data = await res.json();
    const result = data.chart.result[0];
    const timestamps = result.timestamp || [];
    const indicators = result.indicators.quote[0];
    const open = indicators.open || [];
    const high = indicators.high || [];
    const low = indicators.low || [];
    const close = indicators.close || [];
    const volume = indicators.volume || [];

    const formattedData = timestamps.map((ts: number, i: number) => {
      const date = new Date(ts * 1000);
      const timeStr = date.toISOString().split("T")[0];
      return {
        time: timeStr,
        open: open[i] || close[i],
        high: high[i] || close[i],
        low: low[i] || close[i],
        close: close[i],
        volume: volume[i] || 0,
      };
    }).filter((d: any) => d.close !== undefined && d.close !== null);

    return NextResponse.json({
      ticker,
      data: formattedData,
    });
  } catch (error: any) {
    console.error(`Error fetching candlesticks for ${ticker}:`, error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch candlestick data" },
      { status: 500 }
    );
  }
}
