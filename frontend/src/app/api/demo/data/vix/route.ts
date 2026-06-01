import { NextResponse } from "next/server";

export const dynamic = "force-static";

export async function GET() {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/^INDIAVIX?interval=1d&range=2d`,
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
    const meta = result.meta;
    const price = meta.regularMarketPrice;

    let status: "calm" | "caution" | "fear" = "calm";
    if (price >= 20) {
      status = "fear";
    } else if (price >= 15) {
      status = "caution";
    }

    return NextResponse.json({
      vix: price,
      status,
    });
  } catch (error: any) {
    console.error(`Error fetching VIX:`, error);
    return NextResponse.json({
      vix: 15.42,
      status: "caution",
    });
  }
}
