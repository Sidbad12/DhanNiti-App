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
  const resolvedParams = await params;
  const ticker = resolvedParams.ticker;
  const name = ticker.replace(".NS", "");

  const headlinesMap: Record<string, string[]> = {
    RELIANCE: [
      "Reliance Jio targets IPO by late 2026 at over $100 Billion valuation",
      "Reliance Retail expansion gains pace in Tier-2 and Tier-3 cities",
      "Reliance green energy complex in Jamnagar set to begin production",
    ],
    TCS: [
      "TCS signs multi-million dollar cloud migration deal with European banking conglomerate",
      "TCS reports solid Q4 revenue growth driven by digital transformation services",
      "IT sector outlook positive as TCS retains lead in enterprise AI solutions",
    ],
    INFY: [
      "Infosys launches new enterprise generative AI platform 'Topaz'",
      "Infosys expands collaboration with global automotive leaders for smart manufacturing",
      "Infosys reports strong double-digit growth in cloud services segment",
    ],
    HDFCBANK: [
      "HDFC Bank net interest margins stabilize as credit expansion remains healthy",
      "HDFC Bank increases digital loan disbursals with new mobile banking interface",
      "HDFC Bank shares surge on upgrade from international research houses",
    ],
    ICICIBANK: [
      "ICICI Bank reports record net profits driven by strong retail loan growth",
      "ICICI Bank technology upgrades lead to lower customer acquisition costs",
      "Analysts bullish on ICICI Bank capital adequacy ratios and growth runway",
    ],
    SBIN: [
      "State Bank of India asset quality improves with lower NPA ratios",
      "SBI launches digital gold loan schemes to capture rural credit market",
      "SBI dividend declaration triggers positive buying action in banking index",
    ],
    TATAMOTORS: [
      "Tata Motors EV sales hit record highs driven by Punch.ev and Nexon.ev",
      "JLR margin expansion accelerates driving massive free cash flow recovery for Tata Motors",
      "Tata Motors plans demerger of commercial and passenger vehicle units on schedule",
    ],
  };

  const genericHeadlines = [
    `${name} receives analyst upgrades as domestic consumption outlook strengthens`,
    `${name} announces strategic expansion plans into emerging smart manufacturing tech`,
    `${name} institutional inflow surges following recent global MSCI index rebalancing`,
  ];

  const headlines = headlinesMap[name] || genericHeadlines;

  // Generate a mock sentiment
  const isPositive = ticker.startsWith("RELIANCE") || ticker.startsWith("TATAMOTORS") || ticker.startsWith("ICICI");
  const composite = isPositive ? 0.65 : 0.12;
  const positive = isPositive ? 0.7 : 0.3;
  const negative = isPositive ? 0.05 : 0.2;
  const neutral = 1.0 - positive - negative;

  return NextResponse.json({
    ticker,
    headlines,
    sentiment: {
      composite,
      positive,
      negative,
      neutral,
    },
  });
}
