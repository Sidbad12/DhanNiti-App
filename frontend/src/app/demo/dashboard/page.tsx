"use client";
import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import Link from "next/link";
import nifty500Data from "@/lib/nifty500.json";
import {
  logClick, logLoadStart, logLoadSuccess, logLoadError,
  logWs, logPipeline, logNav, logTickerSelect, logConfig, logEvent,
} from "@/lib/logger";

import {
  fetchCurrentPortfolio,
  fetchRecommendation,
  fetchCandlesticks,
  fetchVix,
  fetchNews,
  simulateRebalanceCost,
  getWsUrl,
} from "@/lib/api.demo";
import type {
  PortfolioReport,
  VixResponse,
  NewsResponse,
  WsProgressMessage,
} from "@/types/api";
import dynamic from "next/dynamic";
const ChartLayout = dynamic(
  () => import("@/components/charts/ChartLayout"),
  { ssr: false }
);
const CandleChartDynamic = dynamic(
  () => import("@/components/charts/CandleChart"),
  { ssr: false }
);
const DomPanelDynamic = dynamic(
  () => import("@/components/charts/DomPanel"),
  { ssr: false }
);
const SymbolSearchDynamic = dynamic(
  () => import("@/components/charts/SymbolSearch"),
  { ssr: false }
);
const StockScreenerDynamic = dynamic(
  () => import("@/components/charts/StockScreener"),
  { ssr: false }
);

const mapYfToFyers = (yfTicker: string): string => {
  if (yfTicker.endsWith(".NS")) {
    return `NSE:${yfTicker.slice(0, -3)}-EQ`;
  }
  return yfTicker;
};
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from "recharts";

// ── Constants ─────────────────────────────────────────────────
const G = "#00d97e";
const R = "#ff4d6a";
const DIM = "#1e2d40";

const REGIME_COLORS: Record<string, string> = {
  bull_trending:    "#00d97e",
  bear_trending:    "#ff4d6a",
  high_volatility:  "#f59e0b",
  range_bound:      "#eab308",
  sideways:         "#eab308",
  neutral:          "#64748b",
  unknown:          "#374151",
};

const REGIME_LABELS: Record<string, string> = {
  bull_trending:    "BULL",
  bear_trending:    "BEAR",
  high_volatility:  "HIGH VOL",
  range_bound:      "SIDEWAYS",
  neutral:          "NEUTRAL",
  unknown:          "UNKNOWN",
};

const WS_NODE_LABELS: Record<string, string> = {
  fetch_data:              "Fetching market data",
  fetch_alternative_data:  "Alt data (VIX/FII/sentiment)",
  detect_regime:           "Detecting market regime",
  feature_engineering:     "Computing features",
  drift_check:             "Checking data drift",
  tune_hyperparams:        "Tuning hyperparameters",
  train_classifiers:       "Running XGBoost signals",
  run_predictions:         "SAC RL Inference",
  backtest_and_rl_feedback:"RL feedback loop",
  query_memory:            "Querying Qdrant memory",
  call_advisor:            "Groq synthesis",
  persist_results:         "Saving to Supabase",
  broadcast_websocket:     "Done",
};

const BASE_INDIAN_STOCKS = [
  { ticker: "RELIANCE.NS", name: "Reliance" },
  { ticker: "TCS.NS", name: "TCS" },
  { ticker: "HDFCBANK.NS", name: "HDFC Bank" },
  { ticker: "INFY.NS", name: "Infosys" },
  { ticker: "ICICIBANK.NS", name: "ICICI Bank" },
  { ticker: "ITC.NS", name: "ITC" },
  { ticker: "SBIN.NS", name: "SBI" },
  { ticker: "LT.NS", name: "L&T" },
  { ticker: "TATAMOTORS.NS", name: "Tata Motors" },
  { ticker: "BHARTIARTL.NS", name: "Bharti Airtel" },
];

const SECTOR_GROUPS = [
  {
    id: "financials",
    name: "Financials",
    stocks: [
      { ticker: "HDFCBANK.NS", name: "HDFC Bank" },
      { ticker: "ICICIBANK.NS", name: "ICICI Bank" },
      { ticker: "SBIN.NS", name: "State Bank of India" },
      { ticker: "KOTAKBANK.NS", name: "Kotak Mahindra Bank" },
      { ticker: "AXISBANK.NS", name: "Axis Bank" },
      { ticker: "BAJFINANCE.NS", name: "Bajaj Finance" },
      { ticker: "BAJAJFINSV.NS", name: "Bajaj Finserv" },
      { ticker: "INDUSINDBK.NS", name: "IndusInd Bank" },
      { ticker: "HDFCLIFE.NS", name: "HDFC Life" },
      { ticker: "SBILIFE.NS", name: "SBI Life" },
      { ticker: "FEDERALBNK.NS", name: "Federal Bank" },
      { ticker: "IDFCFIRSTB.NS", name: "IDFC First Bank" },
      { ticker: "BANDHANBNK.NS", name: "Bandhan Bank" },
      { ticker: "MUTHOOTFIN.NS", name: "Muthoot Finance" },
      { ticker: "PNB.NS", name: "Punjab National Bank" },
      { ticker: "CHOLAFIN.NS", name: "Cholamandalam Inv" },
      { ticker: "RBLBANK.NS", name: "RBL Bank" },
      { ticker: "UJJIVANSFB.NS", name: "Ujjivan Small Finance" },
    ]
  },
  {
    id: "it",
    name: "IT",
    stocks: [
      { ticker: "TCS.NS", name: "TCS" },
      { ticker: "INFY.NS", name: "Infosys" },
      { ticker: "WIPRO.NS", name: "Wipro" },
      { ticker: "HCLTECH.NS", name: "HCLTech" },
      { ticker: "TECHM.NS", name: "Tech Mahindra" },
      { ticker: "LTIM.NS", name: "LTIMindtree" },
      { ticker: "PERSISTENT.NS", name: "Persistent Systems" },
      { ticker: "COFORGE.NS", name: "Coforge" },
      { ticker: "MPHASIS.NS", name: "Mphasis" },
      { ticker: "LTTS.NS", name: "L&T Tech" },
      { ticker: "MASTEK.NS", name: "Mastek" },
      { ticker: "KPITTECH.NS", name: "KPIT Tech" },
      { ticker: "TATAELXSI.NS", name: "Tata Elxsi" },
    ]
  },
  {
    id: "energy",
    name: "Energy",
    stocks: [
      { ticker: "RELIANCE.NS", name: "Reliance" },
      { ticker: "ONGC.NS", name: "ONGC" },
      { ticker: "NTPC.NS", name: "NTPC" },
      { ticker: "POWERGRID.NS", name: "Power Grid" },
      { ticker: "COALINDIA.NS", name: "Coal India" },
      { ticker: "BPCL.NS", name: "BPCL" },
    ]
  },
  {
    id: "consumer",
    name: "Consumer",
    stocks: [
      { ticker: "HINDUNILVR.NS", name: "Hindustan Unilever" },
      { ticker: "ITC.NS", name: "ITC" },
      { ticker: "NESTLEIND.NS", name: "Nestle India" },
      { ticker: "BRITANNIA.NS", name: "Britannia" },
      { ticker: "TITAN.NS", name: "Titan" },
      { ticker: "ASIANPAINT.NS", name: "Asian Paints" },
      { ticker: "TATACONSUM.NS", name: "Tata Consumer" },
      { ticker: "DABUR.NS", name: "Dabur" },
      { ticker: "MARICO.NS", name: "Marico" },
      { ticker: "GODREJCP.NS", name: "Godrej CP" },
      { ticker: "COLPAL.NS", name: "Colgate" },
      { ticker: "EMAMILTD.NS", name: "Emami" },
      { ticker: "ZYDUSWELL.NS", name: "Zydus Wellness" },
      { ticker: "JYOTHYLAB.NS", name: "Jyothy Labs" },
    ]
  },
  {
    id: "industrials",
    name: "Industrials",
    stocks: [
      { ticker: "LT.NS", name: "L&T" },
      { ticker: "SIEMENS.NS", name: "Siemens" },
      { ticker: "ABB.NS", name: "ABB India" },
      { ticker: "HAVELLS.NS", name: "Havells" },
      { ticker: "VOLTAS.NS", name: "Voltas" },
      { ticker: "POLYCAB.NS", name: "Polycab" },
      { ticker: "GRINDWELL.NS", name: "Grindwell Norton" },
      { ticker: "KAYNES.NS", name: "Kaynes Tech" },
      { ticker: "APLAPOLLO.NS", name: "APL Apollo" },
      { ticker: "TATASTEEL.NS", name: "Tata Steel" },
      { ticker: "JSWSTEEL.NS", name: "JSW Steel" },
      { ticker: "HINDALCO.NS", name: "Hindalco" },
      { ticker: "ULTRACEMCO.NS", name: "UltraTech" },
      { ticker: "GRASIM.NS", name: "Grasim" },
      { ticker: "SRF.NS", name: "SRF" },
      { ticker: "ATUL.NS", name: "Atul" },
      { ticker: "CUMMINSIND.NS", name: "Cummins India" },
    ]
  },
  {
    id: "auto",
    name: "Auto",
    stocks: [
      { ticker: "TATAMOTORS.NS", name: "Tata Motors" },
      { ticker: "MARUTI.NS", name: "Maruti Suzuki" },
      { ticker: "BAJAJ-AUTO.NS", name: "Bajaj Auto" },
      { ticker: "HEROMOTOCO.NS", name: "Hero MotoCorp" },
      { ticker: "EICHERMOT.NS", name: "Eicher Motors" },
      { ticker: "M&M.NS", name: "M&M" },
      { ticker: "BALKRISIND.NS", name: "Balkrishna Ind" },
      { ticker: "MOTHERSON.NS", name: "Motherson" },
      { ticker: "BOSCHLTD.NS", name: "Bosch" },
    ]
  },
  {
    id: "pharma",
    name: "Pharma",
    stocks: [
      { ticker: "SUNPHARMA.NS", name: "Sun Pharma" },
      { ticker: "DRREDDY.NS", name: "Dr. Reddy's" },
      { ticker: "CIPLA.NS", name: "Cipla" },
      { ticker: "DIVISLAB.NS", name: "Divi's Labs" },
      { ticker: "AUROPHARMA.NS", name: "Aurobindo Pharma" },
      { ticker: "TORNTPHARM.NS", name: "Torrent Pharma" },
      { ticker: "ALKEM.NS", name: "Alkem Labs" },
      { ticker: "IPCALAB.NS", name: "IPCA Labs" },
      { ticker: "GRANULES.NS", name: "Granules India" },
      { ticker: "SUVEN.NS", name: "Suven Life" },
      { ticker: "APOLLOHOSP.NS", name: "Apollo Hospitals" },
    ]
  },
  {
    id: "infra",
    name: "Infra",
    stocks: [
      { ticker: "DLF.NS", name: "DLF" },
      { ticker: "GODREJPROP.NS", name: "Godrej Prop" },
      { ticker: "OBEROIRLTY.NS", name: "Oberoi Realty" },
    ]
  }
];

// ── Helpers ───────────────────────────────────────────────────
const fmt = {
  pct: (v: number) => `${(v * 100).toFixed(2)}%`,
  inr: (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`,
  tick: (t: string) => t.replace(".NS", ""),
  date: (d: string) => new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }),
  conf: (v: number) => `${(v * 100).toFixed(0)}%`,
};

const regimeColor = (r?: string) => (r && REGIME_COLORS[r]) ?? REGIME_COLORS.unknown;
const regimeLabel = (r?: string) => (r && REGIME_LABELS[r]) ?? (r ? r.toUpperCase() : "UNKNOWN");

// ── Sub-components ────────────────────────────────────────────
const KPI = ({ label, value, sub, color = "white" }: { label: string; value: string; sub?: string; color?: string }) => (
  <div className="panel p-4 flex flex-col gap-1">
    <span className="text-[11px] uppercase tracking-widest font-mono" style={{ color: "#64748b" }}>{label}</span>
    <span className="text-2xl font-bold font-mono num" style={{ color }}>{value}</span>
    {sub && <span className="text-[11px] font-mono" style={{ color: "#374151" }}>{sub}</span>}
  </div>
);

const RegimeBadge = ({ regime }: { regime: string }) => (
  <span
    className="font-mono text-[11px] font-bold px-3 py-1 rounded-full uppercase tracking-widest"
    style={{
      color: regimeColor(regime),
      background: `${regimeColor(regime)}18`,
      border: `1px solid ${regimeColor(regime)}44`,
    }}
  >
    {regimeLabel(regime)}
  </span>
);

const renderMessageContent = (content: string) => {
  if (!content) return null;
  const lines = content.split("\n");
  return lines.map((line, lineIndex) => {
    const parts = line.split("**");
    return (
      <div key={lineIndex} className={lineIndex > 0 ? "mt-1" : ""}>
        {parts.map((part, partIndex) => {
          if (partIndex % 2 === 1) {
            return <strong key={partIndex} className="font-semibold text-white">{part}</strong>;
          }
          return part;
        })}
      </div>
    );
  });
};

interface PipelineProgress {
  running: boolean;
  completedNodes: string[];
  currentNode: string;
  error: string | null;
}

// ── Main Dashboard ────────────────────────────────────────────
export default function Dashboard() {
  const [report, setReport] = useState<PortfolioReport | null>(null);
  const [vix, setVix] = useState<VixResponse>({ vix: 0, status: "calm" });
  const [selectedTicker, setSelectedTicker] = useState<string>("");
  const [candleData, setCandleData] = useState<{ time: string; open: number; high: number; low: number; close: number }[]>([]);
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [simCost, setSimCost] = useState<number | null>(null);
  const [portfolioValue, setPortfolioValue] = useState(1000000);
  
  const allocatedTickers = useMemo(() => {
    if (!report) return [];
    const allocs = Object.entries(report.allocations || {})
      .map(([k, v]) => [k, Number(v)] as [string, number])
      .filter(([, w]) => w > 0.01);
    return allocs.map(([t]) => t);
  }, [report]);

  const [carouselIndex, setCarouselIndex] = useState(0);
  const [isCarouselPlaying, setIsCarouselPlaying] = useState(true);

  // Auto-rotation effect
  useEffect(() => {
    if (!isCarouselPlaying || allocatedTickers.length === 0) return;
    const interval = setInterval(() => {
      setCarouselIndex((prev) => (prev + 1) % allocatedTickers.length);
    }, 8000); // rotate every 8 seconds
    return () => clearInterval(interval);
  }, [isCarouselPlaying, allocatedTickers]);

  const carouselTicker = allocatedTickers[carouselIndex] || "";

  const [activeCarouselTicker, setActiveCarouselTicker] = useState("");
  const [fadeState, setFadeState] = useState<"in" | "out">("in");

  useEffect(() => {
    if (!carouselTicker) {
      setActiveCarouselTicker("");
    } else if (!activeCarouselTicker) {
      setActiveCarouselTicker(carouselTicker);
    } else if (carouselTicker !== activeCarouselTicker) {
      setFadeState("out");
      const timeout = setTimeout(() => {
        setActiveCarouselTicker(carouselTicker);
        setFadeState("in");
      }, 300); // match transition duration (300ms)
      return () => clearTimeout(timeout);
    }
  }, [carouselTicker, activeCarouselTicker]);
  // Parse initial tab from URL (e.g. /dashboard/signals -> signals)
  const getInitialTab = () => {
    if (typeof window !== "undefined") {
      const parts = window.location.pathname.split("/");
      const last = parts[parts.length - 1];
      if (["portfolio", "signals", "advisor", "breakdown", "progression"].includes(last)) {
        return last as any;
      }
    }
    return "portfolio";
  };
  const [tab, setTab] = useState<"portfolio" | "signals" | "advisor" | "breakdown" | "progression">(getInitialTab);

  // Sync tab state with browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const parts = window.location.pathname.split("/");
      const last = parts[parts.length - 1];
      if (["portfolio", "signals", "advisor", "breakdown", "progression"].includes(last)) {
        setTab(last as any);
      } else {
        setTab("portfolio");
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const changeTab = (t: "portfolio" | "signals" | "advisor" | "breakdown" | "progression") => {
    logNav(t, tab);
    setTab(t);
    window.history.pushState({}, "", `/dashboard/${t}`);
  };

  const [bookData, setBookData] = useState<any>(null);
  const [candleTimeframe, setCandleTimeframe] = useState("5m");
  const [candleIndicators, setCandleIndicators] = useState<string[]>([]);
  
  const toggleIndicator = (ind: string) => {
    setCandleIndicators(prev => prev.includes(ind) ? prev.filter(i => i !== ind) : [...prev, ind]);
  };
  const [footprintTimeframe, setFootprintTimeframe] = useState("5m");
  const [vpTimeframe, setVpTimeframe] = useState("15m");
  const [loading, setLoading] = useState(true);
  const [recLoading, setRecLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineProgress>({
    running: false, completedNodes: [], currentNode: "", error: null
  });
  const [isUsingFallback, setIsUsingFallback] = useState(false);

  // Start empty — user selects their own universe on first launch
  const [customTickers, setCustomTickers] = useState<string[]>([]);
  const [newTickerInput, setNewTickerInput] = useState("");
  const [startYear, setStartYear] = useState("2022");
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().split("T")[0]);
  const [forceRetrain, setForceRetrain] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [showCustomizer, setShowCustomizer] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSector, setActiveSector] = useState("all");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<{role: string, content: string}[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);

  // Scroll to bottom of chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages]);

  const handleSendChatMessage = async () => {
    if (!chatInput.trim()) return;
    
    const newMessages = [...chatMessages, { role: "user", content: chatInput }];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);
    
    try {
      const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${BASE_URL}/v2/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newMessages }),
      });
      
      if (!res.ok) throw new Error("Chat request failed");
      
      const reader = res.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      
      setChatMessages(prev => [...prev, { role: "assistant", content: "" }]);
      
      if (reader) {
        let done = false;
        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          if (value) {
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.replace("data: ", "").trim();
                if (data === "[DONE]") {
                  done = true;
                  break;
                }
                if (data) {
                  try {
                    const parsed = JSON.parse(data);
                    if (parsed.content) {
                      setChatMessages(prev => {
                        const newMsg = [...prev];
                        newMsg[newMsg.length - 1].content += parsed.content;
                        return newMsg;
                      });
                    } else if (parsed.error) {
                      setChatMessages(prev => {
                        const newMsg = [...prev];
                        newMsg[newMsg.length - 1].content = `⚠️ Backend Error: ${parsed.error}`;
                        return newMsg;
                      });
                    }
                  } catch (e) {
                    // JSON parse error on incomplete chunks
                  }
                }
              }
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setChatMessages(prev => [...prev, { role: "assistant", content: "⚠️ Sorry, I encountered an error connecting to the AI Advisor." }]);
    } finally {
      setChatLoading(false);
    }
  };

  // ── Data fetching ──────────────────────────────────────────
  const loadReport = useCallback(async () => {
    logLoadStart("Portfolio Report", { endpoint: "/v2/portfolio/current" });
    try {
      const { report: data, isUsingFallback: fallbackUsed, error } = await fetchCurrentPortfolio();
      if (!data) {
        logLoadError("Portfolio Report", new Error(error ?? "No V2 portfolio data available. Run the pipeline first."));
        setErr(error ?? "No V2 portfolio data available. Run the pipeline first.");
        logEvent("No portfolio found — showing Setup Wizard");
        setShowSetup(true);
        return;
      }
      setReport(data);
      setIsUsingFallback(fallbackUsed);
      logLoadSuccess("Portfolio Report", {
        regime: data.regime ?? "unknown",
        tickers: data.tickers?.length ?? 0,
        source: fallbackUsed ? "Supabase fallback" : "FastAPI",
        report_date: data.report_date ?? "?",
        model_version: data.model_version ?? "?",
      });
      if (data.tickers?.length) {
        setCustomTickers(data.tickers);
      }
      if (data.start_date) {
        const year = data.start_date.split("-")[0];
        if (year && year.length === 4) {
          setStartYear(year);
        }
      }
      // Set first ticker as default selection
      if (data.tickers?.length && !selectedTicker) {
        setSelectedTicker(data.tickers[0]);
      }
      setErr(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      logLoadError("Portfolio Report", e);
      setErr(msg);
      // No report available — drop straight to the Configurator wizard
      logEvent("No portfolio found — showing Setup Wizard");
      setShowSetup(true);
    } finally {
      setLoading(false);
    }
  }, [selectedTicker]);

  const loadVix = useCallback(async () => {
    logLoadStart("India VIX", { endpoint: "/data/vix" });
    try {
      const v = await fetchVix();
      setVix(v);
      logLoadSuccess("India VIX", { vix: v.vix, status: v.status });
    } catch (e) {
      logLoadError("India VIX", e);
    }
  }, []);

  useEffect(() => {
    const checkTauriEnv = async () => {
      if (typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          const exists = await invoke("check_env_exists");
          if (!exists) {
            window.location.href = "/setup";
            return true;
          }
        } catch (e) {
          console.error("Failed to check env existence:", e);
        }
      }
      return false;
    };

    checkTauriEnv().then((redirected) => {
      if (!redirected) {
        loadReport();
        loadVix();
      }
    });
  }, [loadReport, loadVix]);

  // ── WebSocket ──────────────────────────────────────────────
  useEffect(() => {
    const wsUrl = getWsUrl();
    let ws: WebSocket;
    let reconnectTimer: NodeJS.Timeout;
    const TOTAL_NODES = Object.keys(WS_NODE_LABELS).length;

    const connectWs = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          logWs("Connected", { url: wsUrl });
        };
        ws.onmessage = (event) => {
          try {
            const msg: WsProgressMessage = JSON.parse(event.data);
            if (msg.type === "system") {
              if (msg.status === "running") {
                logWs("Pipeline started", { status: msg.status });
                setPipeline(p => ({ ...p, running: true, currentNode: "Starting..." }));
              } else if (msg.status === "completed") {
                logWs("Pipeline completed ✅", { status: msg.status });
                setPipeline(p => ({ ...p, running: false, currentNode: "" }));
                loadReport();
                loadVix();
              } else if (msg.status === "error") {
                logWs("Pipeline error ❌", { message: msg.message });
                setPipeline(p => ({ ...p, running: false, error: msg.message ?? "Pipeline error" }));
              }
            } else if (msg.type === "progress" && msg.node) {
              setPipeline(p => {
                const newCompleted = p.completedNodes.includes(msg.node!)
                  ? p.completedNodes
                  : [...p.completedNodes, msg.node!];
                logPipeline(
                  msg.node!,
                  WS_NODE_LABELS[msg.node!] ?? msg.node!,
                  newCompleted.length,
                  TOTAL_NODES
                );
                return { ...p, running: true, currentNode: msg.node!, completedNodes: newCompleted };
              });
            }
          } catch { /* ignore malformed messages */ }
        };
        ws.onclose = () => {
          logWs("Disconnected — reconnecting in 3s", { url: wsUrl });
          reconnectTimer = setTimeout(connectWs, 3000);
        };
        ws.onerror = (e) => {
          logWs("WebSocket error", { event: String(e) });
        };
        wsRef.current = ws;
      } catch (e) {
        logWs("Connection failed — retrying in 3s", { error: String(e) });
        reconnectTimer = setTimeout(connectWs, 3000);
      }
    };

    connectWs();

    return () => {
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect loop on unmount
        wsRef.current.close();
        logWs("Closed on unmount");
      }
    };
  }, [loadReport, loadVix]);

  // ── Ticker data ────────────────────────────────────────────
  useEffect(() => {
    if (!selectedTicker) return;
    logTickerSelect(selectedTicker, "chart + news load triggered");
    setCandleData([]);
    setNews(null);

    logLoadStart("Candlesticks", { ticker: selectedTicker, endpoint: `/data/candlesticks/${selectedTicker}` });
    fetchCandlesticks(selectedTicker)
      .then(d => {
        setCandleData(d.data);
        logLoadSuccess("Candlesticks", { ticker: selectedTicker, candles: d.data.length });
      })
      .catch(e => logLoadError("Candlesticks", e));

    logLoadStart("News", { ticker: selectedTicker, endpoint: `/data/news/${selectedTicker}` });
    setNewsLoading(true);
    fetchNews(selectedTicker)
      .then(n => {
        setNews(n);
        logLoadSuccess("News", { ticker: selectedTicker, articles: (n as { items?: unknown[] }).items?.length ?? "?" });
      })
      .catch(e => logLoadError("News", e))
      .finally(() => setNewsLoading(false));
  }, [selectedTicker]);

  // ── Actions ────────────────────────────────────────────────
  const runRecommendation = async () => {
    logClick("Run Recommendation Pipeline", {
      tickers: customTickers.join(", "),
      startYear,
      asOfDate,
      forceRetrain,
      tickerCount: customTickers.length,
    });
    setRecLoading(true);
    setSimCost(null);
    setPipeline({ running: true, completedNodes: [], currentNode: "Initializing...", error: null });
    try {
      const formattedStartDate = `${startYear}-01-01`;
      logLoadStart("V2 Portfolio Recommendation", {
        endpoint: "/v2/portfolio/recommend",
        tickers: customTickers,
        startDate: formattedStartDate,
        asOfDate,
        forceRetrain,
      });
      const data = await fetchRecommendation(true, true, customTickers, formattedStartDate, forceRetrain, asOfDate);
      setReport(data);
      setIsUsingFallback(false);
      setShowSetup(false);
      setPipeline(p => ({ ...p, running: false }));
      logLoadSuccess("V2 Portfolio Recommendation", {
        regime: data.regime ?? "unknown",
        confidence: data.llm_confidence ?? "?",
        expected_return: data.expected_return ?? "?",
        tickers: data.tickers?.length ?? 0,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Recommendation failed";
      logLoadError("V2 Portfolio Recommendation", e);
      setPipeline({ running: false, completedNodes: [], currentNode: "", error: msg });
    } finally {
      setRecLoading(false);
    }
  };

  const handleResetSetup = () => {
    logClick("Reset Setup Wizard", { previousTickers: customTickers.length });
    setReport(null);
    setCustomTickers([]);          // empty — user rebuilds their own universe
    setStartYear("2022");
    setAsOfDate(new Date().toISOString().split("T")[0]);
    setForceRetrain(true);
    setShowSetup(true);
    logEvent("Setup Wizard opened (reset)", {});
  };

  const runSimulation = async () => {
    if (!report) return;
    const targetWeights = report.sac_allocations ?? report.ppo_allocations ?? report.allocations ?? {};
    const tickers = Object.keys(targetWeights);
    const currentWeights = tickers.reduce<Record<string, number>>(
      (acc, t) => ({ ...acc, [t]: 1 / tickers.length }),
      {}
    );
    logClick("Simulate Rebalance Cost", {
      portfolioValue,
      tickers: tickers.join(", "),
      tickerCount: tickers.length,
    });
    logLoadStart("Rebalance Cost Simulation", { endpoint: "/simulate/rebalance-cost", portfolioValue });
    try {
      const res = await simulateRebalanceCost(currentWeights, targetWeights, portfolioValue);
      setSimCost(res.estimated_cost_inr);
      logLoadSuccess("Rebalance Cost Simulation", {
        estimated_cost_inr: res.estimated_cost_inr,
        portfolioValue,
      });
    } catch (e) {
      logLoadError("Rebalance Cost Simulation", e);
    }
  };

  // ── Allocation data ────────────────────────────────────────
  const allocations = report
    ? Object.entries(report.sac_allocations ?? report.ppo_allocations ?? report.allocations ?? {})
        .sort(([, a], [, b]) => b - a)
    : [];

  interface BreakdownEntry {
    ticker: string;
    xgb_signal?: string;
    action?: string;
    xgb_confidence?: number;
    confidence?: number;
    note?: string;
    llm_note?: string;
    final_weight?: number;
    [key: string]: unknown;
  }

  const breakdownMap: Record<string, BreakdownEntry> = report?.stock_breakdowns
    ? Object.fromEntries(
        (Array.isArray(report.stock_breakdowns)
          ? report.stock_breakdowns
          : Object.entries(report.stock_breakdowns).map(([ticker, v]: [string, unknown]) => ({ ticker, ...(v as object) }))
        ).map((s: BreakdownEntry) => [s.ticker, s])
      )
    : {};

  // ── Pipeline progress overlay nodes ───────────────────────
  const ORDERED_NODES = Object.keys(WS_NODE_LABELS);

  // ── Reusable pipeline progress bar ───────────────────────
  const PipelineProgressBar = ({ compact = false }: { compact?: boolean }) => {
    const total = ORDERED_NODES.length;
    const doneCount = pipeline.completedNodes.length;
    const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0;
    const activeIdx = ORDERED_NODES.indexOf(pipeline.currentNode);
    const currentLabel = WS_NODE_LABELS[pipeline.currentNode] ?? pipeline.currentNode ?? "Initializing...";

    if (compact) {
      // Slim banner for the sticky dashboard overlay
      return (
        <div className="flex items-center gap-4 w-full">
          {/* Spinner */}
          <div className="w-3.5 h-3.5 border-2 rounded-full animate-spin shrink-0"
            style={{ borderColor: `${G} transparent transparent transparent` }} />
          {/* Label */}
          <span className="font-mono text-[10px] font-bold whitespace-nowrap" style={{ color: G }}>
            {currentLabel.toUpperCase()}
          </span>
          {/* Segmented track */}
          <div className="flex-1 flex gap-0.5 h-1.5 rounded-full overflow-hidden">
            {ORDERED_NODES.map((node, i) => {
              const done = pipeline.completedNodes.includes(node);
              const active = i === activeIdx;
              return (
                <div
                  key={node}
                  className="flex-1 rounded-full transition-all duration-500"
                  style={{
                    background: done ? G : active ? `${G}88` : `${DIM}66`,
                    boxShadow: active ? `0 0 6px ${G}` : "none",
                  }}
                />
              );
            })}
          </div>
          {/* Pct */}
          <span className="font-mono text-[10px] font-bold shrink-0" style={{ color: "#64748b" }}>
            {pct}%
          </span>
        </div>
      );
    }

    // Full card for the setup wizard
    return (
      <div className="space-y-3">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 rounded-full animate-spin"
              style={{ borderColor: `${G} transparent transparent transparent` }} />
            <span className="font-mono text-xs font-bold uppercase tracking-widest text-white">
              {currentLabel}
            </span>
          </div>
          <span className="font-mono text-sm font-bold" style={{ color: G }}>{pct}%</span>
        </div>

        {/* Main progress bar */}
        <div className="relative h-2 rounded-full overflow-hidden" style={{ background: DIM }}>
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${pct}%`,
              background: `linear-gradient(90deg, ${G}99, ${G})`,
              boxShadow: `0 0 12px ${G}88`,
            }}
          />
        </div>

        {/* Segmented step track */}
        <div className="flex gap-1">
          {ORDERED_NODES.map((node, i) => {
            const done = pipeline.completedNodes.includes(node);
            const active = i === activeIdx;
            return (
              <div
                key={node}
                title={WS_NODE_LABELS[node]}
                className="flex-1 h-1 rounded-full transition-all duration-500"
                style={{
                  background: done ? G : active ? `${G}77` : `${DIM}`,
                  boxShadow: active ? `0 0 8px ${G}` : "none",
                }}
              />
            );
          })}
        </div>

        {/* Step labels */}
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {ORDERED_NODES.map((node, i) => {
            const done = pipeline.completedNodes.includes(node);
            const active = i === activeIdx;
            return (
              <span key={node} className="font-mono text-[9px] flex items-center gap-1"
                style={{ color: done ? "#334155" : active ? "#f59e0b" : "#1e293b" }}>
                <span style={{ color: done ? G : active ? "#f59e0b" : "#1e2d40" }}>
                  {done ? "✓" : active ? "▶" : "·"}
                </span>
                <span style={{ color: done ? "#475569" : active ? "#fbbf24" : "#374151" }}>
                  {WS_NODE_LABELS[node]}
                </span>
              </span>
            );
          })}
        </div>

        {pipeline.error && (
          <div className="font-mono text-xs text-red-400 border border-red-500/20 p-2.5 rounded bg-red-500/5">
            ✗ Error: {pipeline.error}
          </div>
        )}
      </div>
    );
  };

  // ── Loading state ──────────────────────────────────────────
  if (loading) return (
    <div className="flex h-screen items-center justify-center" style={{ background: "#070a0f" }}>
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 rounded-full animate-spin"
          style={{ borderColor: `${G} transparent transparent transparent` }} />
        <span className="font-mono text-sm" style={{ color: "#64748b" }}>Loading DhanNiti...</span>
      </div>
    </div>
  );

  if (showSetup || !report) {
    return (
      <div className="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 animate-fade-in" style={{ background: "#070a0f" }}>
        <div className="max-w-4xl w-full space-y-8 p-8 rounded-2xl border transition-all duration-500 shadow-2xl animate-fade-in-up" style={{ borderColor: `${G}22`, background: "linear-gradient(180deg, #0b131f 0%, #070a0f 100%)" }}>
          
          <div className="text-center space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-mono text-[10px] font-bold tracking-widest" style={{ background: `${G}12`, color: G, border: `1px solid ${G}33` }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: G }} />
              COGNITIVE AGENT WIZARD
            </div>
            <h1 className="text-4xl font-extrabold text-white tracking-tight sm:text-5xl">
              DhanNiti <span style={{ color: G }}>V2 Configurator</span>
            </h1>
            <p className="text-slate-400 text-sm max-w-xl mx-auto">
              Initialize a clean-state universe for Indian markets. Choose your base tickers, historical start year, and train a fresh set of XGBoost classifiers.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 border-t border-b py-8" style={{ borderColor: `${DIM}44` }}>
            {/* Left Column: Stock Universe Builder */}
            <div className="space-y-4">
              {/* Header with count */}
              <div className="flex items-center justify-between">
                <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">
                  1. Build Your Stock Universe
                </label>
                <div className="flex items-center gap-2">
                  <span
                    className="font-mono text-[11px] font-bold px-2.5 py-0.5 rounded-full"
                    style={{
                      background: customTickers.length > 0 ? `${G}18` : "#1e2d40",
                      color: customTickers.length > 0 ? G : "#64748b",
                      border: `1px solid ${customTickers.length > 0 ? G : DIM}`,
                    }}
                  >
                    {customTickers.length} / {(nifty500Data as { ticker: string; name: string }[]).length} selected
                  </span>
                  {customTickers.length > 0 && (
                    <button
                      type="button"
                      onClick={() => { logClick("Clear All Tickers"); setCustomTickers([]); }}
                      className="font-mono text-[10px] px-2 py-0.5 rounded border"
                      style={{ color: "#f87171", borderColor: "#f8717133", background: "#f871710a" }}
                    >
                      Clear All
                    </button>
                  )}
                </div>
              </div>

              {/* Search */}
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="🔍 Search 2,100+ NSE stocks by name or symbol..."
                  className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg outline-none"
                  style={{ background: "#0d1117", color: "white", border: `1px solid ${DIM}` }}
                />
                {/* Autocomplete */}
                {searchQuery.trim().length >= 2 && (() => {
                  const query = searchQuery.toLowerCase().trim();
                  const matches = (nifty500Data as { ticker: string; name: string }[])
                    .filter(s => s.name.toLowerCase().includes(query) || s.ticker.toLowerCase().includes(query))
                    .slice(0, 8);
                  const showForceAdd = !matches.some(s =>
                    s.ticker.toLowerCase() === query || s.ticker.toLowerCase().replace(".ns", "") === query
                  );
                  if (matches.length === 0 && !showForceAdd) return null;
                  return (
                    <div className="absolute left-0 right-0 mt-1 rounded-lg shadow-2xl border z-50 overflow-hidden"
                      style={{ background: "#0d1117", borderColor: DIM }}>
                      {matches.map(stock => {
                        const alreadyAdded = customTickers.includes(stock.ticker);
                        return (
                          <button key={stock.ticker} type="button"
                            onClick={() => { if (!alreadyAdded) setCustomTickers([...customTickers, stock.ticker]); setSearchQuery(""); }}
                            className="w-full text-left px-4 py-2.5 hover:bg-[#00d97e]/10 text-xs font-mono flex items-center justify-between transition-colors border-b last:border-b-0"
                            style={{ borderColor: `${DIM}33` }}>
                            <span className="truncate mr-2" style={{ color: alreadyAdded ? "#64748b" : "white" }}>
                              {stock.name}{alreadyAdded && " ✓"}
                            </span>
                            <span className="font-bold shrink-0" style={{ color: G }}>{stock.ticker.replace(".NS", "")}</span>
                          </button>
                        );
                      })}
                      {showForceAdd && (() => {
                        const clean = searchQuery.toUpperCase().includes(".") ? searchQuery.toUpperCase() : `${searchQuery.toUpperCase()}.NS`;
                        return (
                          <button type="button"
                            onClick={() => { if (!customTickers.includes(clean)) setCustomTickers([...customTickers, clean]); setSearchQuery(""); }}
                            className="w-full text-left px-4 py-2.5 hover:bg-yellow-500/10 text-xs font-mono flex items-center justify-between border-t border-dashed"
                            style={{ borderColor: `${DIM}55` }}>
                            <span className="font-bold text-yellow-400">+ Force Add</span>
                            <span className="font-bold shrink-0" style={{ color: G }}>{clean}</span>
                          </button>
                        );
                      })()}
                    </div>
                  );
                })()}
              </div>

              {/* Power Presets */}
              <div className="space-y-2">
                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Quick Presets</span>
                <div className="grid grid-cols-2 gap-2">
                  {/* V2 Training Universe */}
                  <button type="button"
                    onClick={() => {
                      logClick("Preset: V2 Universe");
                      const v2Universe = SECTOR_GROUPS.flatMap(g => g.stocks.map(s => s.ticker));
                      setCustomTickers(Array.from(new Set(v2Universe)));
                    }}
                    className="p-2.5 rounded-lg border text-center transition-all hover:scale-[1.02]"
                    style={{ background: "#111827", borderColor: "#c9a84c44", color: "#c9a84c" }}
                  >
                    <div className="font-mono text-[11px] font-bold">V2 UNIVERSE</div>
                    <div className="font-mono text-[9px] text-slate-500 mt-0.5">~130 stocks</div>
                  </button>

                  {/* Nifty 50 */}
                  <button type="button"
                    onClick={() => {
                      logClick("Preset: Nifty 50");
                      const nifty50 = [
                        "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
                        "HINDUNILVR.NS","ITC.NS","KOTAKBANK.NS","LT.NS","AXISBANK.NS",
                        "SBIN.NS","BHARTIARTL.NS","ASIANPAINT.NS","BAJFINANCE.NS","HCLTECH.NS",
                        "MARUTI.NS","SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","NESTLEIND.NS",
                        "WIPRO.NS","NTPC.NS","POWERGRID.NS","TATAMOTORS.NS","JSWSTEEL.NS",
                        "ADANIENT.NS","ADANIPORTS.NS","TATASTEEL.NS","ONGC.NS","COALINDIA.NS",
                        "BPCL.NS","DRREDDY.NS","DIVISLAB.NS","CIPLA.NS","BAJAJFINSV.NS",
                        "GRASIM.NS","INDUSINDBK.NS","M&M.NS","TATACONSUM.NS","APOLLOHOSP.NS",
                        "BAJAJ-AUTO.NS","HEROMOTOCO.NS","EICHERMOT.NS","HINDALCO.NS","SBILIFE.NS",
                        "HDFCLIFE.NS","TECHM.NS","LTIM.NS","BRITANNIA.NS","DABUR.NS",
                      ];
                      setCustomTickers(nifty50);
                    }}
                    className="p-2.5 rounded-lg border text-center transition-all hover:scale-[1.02]"
                    style={{ background: "#111827", borderColor: "#3b82f644", color: "#60a5fa" }}
                  >
                    <div className="font-mono text-[11px] font-bold">NIFTY 50</div>
                    <div className="font-mono text-[9px] text-slate-500 mt-0.5">50 stocks</div>
                  </button>
                </div>
              </div>

              {/* Sector Filter Tabs */}
              <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-thin" style={{ borderBottom: `1px solid ${DIM}44` }}>
                <button type="button"
                  onClick={() => setActiveSector("all")}
                  className="px-2.5 py-1 rounded text-[10px] font-mono font-bold whitespace-nowrap transition-all"
                  style={{ background: activeSector === "all" ? G : "transparent", color: activeSector === "all" ? "#000" : "#64748b" }}>
                  ALL
                </button>
                {SECTOR_GROUPS.map(g => {
                  const sectorTickers = g.stocks.map(s => s.ticker);
                  const allSel = sectorTickers.every(t => customTickers.includes(t));
                  return (
                    <button key={g.id} type="button"
                      className="px-2.5 py-1 rounded text-[10px] font-mono font-bold whitespace-nowrap flex items-center gap-1 transition-all"
                      style={{
                        background: activeSector === g.id ? (allSel ? G : `${G}22`) : "transparent",
                        color: activeSector === g.id ? (allSel ? "#000" : G) : "#64748b",
                      }}
                      onClick={() => setActiveSector(g.id)}>
                      {g.name.toUpperCase()}
                      {allSel && <span style={{ color: activeSector === g.id ? "#000" : G, fontSize: 8 }}>✓</span>}
                    </button>
                  );
                })}
              </div>


              {/* Stock Grid — from nifty500Data when in ALL view, sector stocks when filtered */}
              <div className="grid grid-cols-2 gap-1.5 max-h-[220px] overflow-y-auto pr-1">
                {(() => {
                  const allNseStocks = nifty500Data as { ticker: string; name: string }[];
                  const sectorStocks = SECTOR_GROUPS.flatMap(g =>
                    g.stocks.map(s => ({ ...s, sectorId: g.id }))
                  );

                  let pool: { ticker: string; name: string }[];
                  if (activeSector === "all") {
                    // Show all NSE stocks when in "all" view, filtered by search
                    pool = searchQuery.trim().length >= 1
                      ? allNseStocks.filter(s =>
                          s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          s.ticker.toLowerCase().includes(searchQuery.toLowerCase())
                        ).slice(0, 100)          // cap at 100 for perf when browsing
                      : sectorStocks;             // no search → show organised sector stocks
                  } else {
                    const grp = SECTOR_GROUPS.find(g => g.id === activeSector);
                    pool = (grp?.stocks ?? []).filter(s =>
                      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                      s.ticker.toLowerCase().includes(searchQuery.toLowerCase())
                    );
                  }

                  if (pool.length === 0) return (
                    <div className="col-span-2 text-center py-4 text-xs font-mono text-slate-500">
                      No matching stocks. Try the search bar above.
                    </div>
                  );

                  return pool.map(stock => {
                    const selected = customTickers.includes(stock.ticker);
                    return (
                      <button key={stock.ticker} type="button"
                        onClick={() => {
                          if (selected) setCustomTickers(customTickers.filter(t => t !== stock.ticker));
                          else setCustomTickers([...customTickers, stock.ticker]);
                        }}
                        className="flex items-center justify-between p-2 rounded-lg border font-mono text-[11px] text-left transition-all hover:opacity-90"
                        style={{
                          background: selected ? `${G}0c` : "#0d1117",
                          borderColor: selected ? G : `${DIM}44`,
                          color: selected ? "white" : "#64748b",
                        }}>
                        <span className="truncate max-w-[120px]">{stock.name}</span>
                        <span className="text-[9px] opacity-80 shrink-0 font-bold ml-1" style={{ color: selected ? G : "#475569" }}>
                          {stock.ticker.replace(".NS", "")}
                        </span>
                      </button>
                    );
                  });
                })()}
              </div>

              {/* Selected Tickers Preview */}
              {customTickers.length > 0 && (
                <div className="space-y-2 pt-3 border-t" style={{ borderColor: `${DIM}33` }}>
                  <div className="flex items-center justify-between">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
                      Selected ({customTickers.length})
                    </label>
                    <button type="button"
                      onClick={() => setCustomTickers([])}
                      className="text-[10px] font-mono text-red-400 hover:text-red-300">
                      Clear All
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5 p-2.5 rounded-xl max-h-[100px] overflow-y-auto" style={{ background: "#0b1119" }}>
                    {customTickers.map(t => (
                      <span key={t} className="font-mono text-[10px] px-2 py-0.5 rounded flex items-center gap-1"
                        style={{ background: "#111827", color: "#94a3b8", border: `1px solid ${DIM}` }}>
                        {t.replace(".NS", "")}
                        <button type="button" onClick={() => setCustomTickers(customTickers.filter(x => x !== t))}
                          className="text-red-500 hover:text-red-400 font-bold leading-none">×</button>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {customTickers.length === 0 && (
                <div className="text-center py-3 font-mono text-[11px] text-slate-500 border border-dashed rounded-lg"
                  style={{ borderColor: `${DIM}44` }}>
                  No stocks selected — pick a preset above or search for stocks
                </div>
              )}
            </div>

            {/* Right Column: Parameters Selection */}
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">
                  2. Historical Window Start Year
                </label>
                <select
                  value={startYear}
                  onChange={(e) => {
                    logConfig("startYear", e.target.value);
                    setStartYear(e.target.value);
                  }}
                  className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg outline-none cursor-pointer"
                  style={{ background: "#0d1117", color: "white", border: `1px solid ${DIM}` }}
                >
                  {["2018", "2019", "2020", "2021", "2022", "2023", "2024"].map((yr) => (
                    <option key={yr} value={yr}>
                      {yr} (feeds {new Date().getFullYear() - parseInt(yr)}y+ of market pattern memory)
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-500 italic">
                  * Note: Regardless of year chosen, history is downloaded to let the agent study patterns and feed Qdrant/Groq narrative engine.
                </p>
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">
                  3. Inference Anchor Date (As of)
                </label>
                <input
                  type="date"
                  value={asOfDate}
                  onChange={(e) => {
                    logConfig("asOfDate", e.target.value);
                    setAsOfDate(e.target.value);
                  }}
                  onClick={(e) => e.currentTarget.showPicker()}
                  className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg outline-none cursor-pointer"
                  style={{ background: "#0d1117", color: "white", border: `1px solid ${DIM}` }}
                />
              </div>

              <div className="flex items-center justify-between p-3.5 rounded-lg border" style={{ background: "#0d1117", borderColor: `${DIM}77` }}>
                <div className="space-y-0.5">
                  <span className="block text-xs font-mono text-white">4. Fresh XGBoost Fit</span>
                  <span className="block text-[10px] text-slate-500">Fit fresh directional classifiers for each stock.</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    logConfig("forceRetrain", !forceRetrain);
                    setForceRetrain(!forceRetrain);
                  }}
                  className="px-3 py-1.5 rounded text-xs font-mono font-bold transition-all"
                  style={{
                    background: forceRetrain ? `${G}0c` : "#1e2d40",
                    border: `1px solid ${forceRetrain ? G : DIM}`,
                    color: forceRetrain ? G : "#64748b",
                  }}
                >
                  {forceRetrain ? "ENABLED" : "DISABLED"}
                </button>
              </div>
            </div>
          </div>



          {/* Action button / Running state */}
          <div className="space-y-4 pt-4">
            {recLoading || pipeline.running ? (
              <div className="p-5 rounded-xl border" style={{ background: "#09121a", borderColor: `${G}33` }}>
                <PipelineProgressBar />
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row gap-3">
                {report && (
                  <button
                    type="button"
                    onClick={() => { logClick("Cancel Setup"); setShowSetup(false); }}
                    className="flex-1 px-5 py-4 text-xs font-mono font-bold rounded-lg border transition-all text-slate-400 hover:text-white"
                    style={{ background: "#0d1117", borderColor: DIM }}
                  >
                    Cancel Setup
                  </button>
                )}
                <button
                  type="button"
                  onClick={runRecommendation}
                  disabled={customTickers.length === 0}
                  className="flex-2 flex-grow px-8 py-4 text-sm font-mono font-bold text-black rounded-lg transition-all hover:shadow-[0_0_20px_rgba(0,217,126,0.3)] hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed select-none"
                  style={{ background: G }}
                >
                  START DHANNITI AGENT INFRASTRUCTURE
                </button>
              </div>
            )}
          </div>

        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "#070a0f" }}>
      {/* ── Sidebar ───────────────────────────────────────────── */}
      <aside
        className={`flex flex-col transition-all duration-300 ease-in-out border-r shrink-0 ${
          isSidebarOpen ? "w-64" : "w-0 opacity-0 overflow-hidden border-transparent"
        }`}
        style={{ background: "#0b131f", borderColor: DIM }}
      >
        <div className="h-16 flex items-center px-6 border-b shrink-0" style={{ borderColor: DIM }}>
          <span className="text-white font-bold text-xl tracking-tight flex items-center gap-2" style={{ whiteSpace: "nowrap" }}>
            <span style={{ fontFamily: "'Yatra One', system-ui", color: 'white' }}>धन</span>
            <em style={{ fontStyle: 'italic', color: G, fontFamily: "'Playfair Display', serif" }}>Niti</em>
          </span>
        </div>
        <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
          <div className="text-[10px] font-mono text-slate-500 mb-2 uppercase tracking-widest pl-2">Dashboard Views</div>
          
          {(["portfolio", "signals", "advisor", "breakdown", "progression"] as const).map(t => (
            <button
              key={t}
              onClick={() => changeTab(t)}
              className={`w-full text-left font-mono text-xs px-4 py-3 rounded-lg text-slate-300 hover:text-white border transition-all flex items-center gap-2 hover:bg-[#152132] ${tab === t ? "bg-[#0f2618] border-[#00d97e]/40" : "bg-[#111827] border-[#1e2d40]"}`}
              style={{ whiteSpace: "nowrap" }}
            >
              <span style={{ color: G }}>{
                t === "portfolio" ? "◈" : 
                t === "signals" ? "⚡" : 
                t === "advisor" ? "✦" : 
                t === "breakdown" ? "◱" : "⚙"
              }</span> {
                t === "portfolio" ? "DASHBOARD" :
                t === "advisor" ? "SAC ALLOCATIONS" :
                t === "progression" ? "ML WORKFLOW" :
                t.toUpperCase()
              }
            </button>
          ))}

          <div className="text-[10px] font-mono text-slate-500 mt-8 mb-2 uppercase tracking-widest pl-2">External Apps</div>
          <Link
            href="/holdings"
            className="font-mono text-xs px-4 py-3 rounded-lg bg-[#111827] text-slate-300 hover:text-white border border-[#1e2d40] hover:border-[#00d97e]/40 transition-all flex items-center gap-2 hover:bg-[#152132]"
            style={{ whiteSpace: "nowrap" }}
          >
            <span style={{ color: G }}>≡</span> LEDGER
          </Link>
          <Link
            href="/charts"
            className="font-mono text-xs px-4 py-3 rounded-lg bg-[#111827] text-slate-300 hover:text-white border border-[#1e2d40] hover:border-[#00d97e]/40 transition-all flex items-center gap-2 hover:bg-[#152132]"
            style={{ whiteSpace: "nowrap" }}
          >
            <span style={{ color: G }}>◱</span> CHARTS
          </Link>
        </nav>
      </aside>

      {/* ── Main Content Area ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto relative">
        {/* ── Header ───────────────────────────────────────────── */}
        <header
          className="sticky top-0 z-50 px-6 h-16 flex items-center justify-between shrink-0"
          style={{ background: "#0d1117", borderBottom: `1px solid ${DIM}` }}
        >
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-1.5 rounded-md hover:bg-[#1e2d40] transition-colors text-slate-400 hover:text-white focus:outline-none"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
          </div>

        <div className="flex items-center gap-3">
          {/* VIX pill */}
          <div className="items-center gap-2 px-2 py-1 rounded hidden md:flex"
            style={{ border: `1px solid ${DIM}`, background: "#111827" }}>
            <span className="font-mono text-[10px] uppercase tracking-widest text-[#64748b]">INDIA VIX</span>
            <span className="font-mono text-sm font-bold" style={{
              color: vix.status === "fear" ? R : vix.status === "caution" ? "#f59e0b" : G
            }}>
              {vix.vix > 0 ? vix.vix.toFixed(2) : "—"}
            </span>
          </div>

          {/* Regime badge */}
          {report && <RegimeBadge regime={report.regime} />}

          {/* Reset Cleanstate button */}
          <button
            onClick={handleResetSetup}
            disabled={recLoading}
            className="px-3 py-1 text-xs font-mono font-bold rounded transition-colors text-yellow-500 border border-yellow-500/30 bg-yellow-500/5 hover:bg-yellow-500/10"
          >
            RESET CLEANSTATE
          </button>

          {/* Refresh button */}
          <button
            onClick={loadReport}
            disabled={recLoading}
            className="px-3 py-1 text-xs font-mono font-bold rounded transition-colors"
            style={{ background: "#111827", color: "#64748b", border: `1px solid ${DIM}` }}
            onClickCapture={() => logClick("Refresh Portfolio")}
          >
            REFRESH
          </button>

          {/* Run pipeline button */}
          {pipeline.running ? (
            <div className="flex items-center gap-2 px-3 py-1 rounded" style={{ background: "#0f2618", border: `1px solid ${G}33` }}>
              <div className="w-2 h-2 rounded-full" style={{ background: G }} />
              <span className="font-mono text-xs font-bold" style={{ color: G }}>
                {WS_NODE_LABELS[pipeline.currentNode] ?? pipeline.currentNode.toUpperCase()}
              </span>
            </div>
          ) : (
            <button
              onClick={runRecommendation}
              disabled={recLoading || isUsingFallback}
              title={isUsingFallback ? "Local FastAPI server is offline. Direct Supabase read mode." : ""}
              className="px-3 py-1 text-xs font-mono font-bold text-black rounded transition-all hover:opacity-90 disabled:opacity-50"
              style={{
                background: isUsingFallback ? "#1e293b" : G,
                color: isUsingFallback ? "#64748b" : "black",
                border: isUsingFallback ? "1px solid #334155" : "none"
              }}
            >
              {recLoading ? "RUNNING..." : "RUN PIPELINE"}
            </button>
          )}

          {/* Date */}
          {report && (
            <span className="font-mono text-[11px] hidden lg:block" style={{ color: "#64748b" }}>
              {fmt.date(report.date ?? report.as_of ?? "")}
            </span>
          )}
        </div>
      </header>



      {/* ── Pipeline Progress Overlay ─────────────────────── */}
      {(recLoading || pipeline.running) && (
        <div className="px-6 py-3" style={{ background: "#04090f", borderBottom: `1px solid ${G}22` }}>
          <PipelineProgressBar compact />
        </div>
      )}

      {/* ── Error banner ──────────────────────────────────── */}
      {err && !report && (
        <div className="mx-6 mt-4 p-4 rounded-lg flex items-center gap-3"
          style={{ background: "#ff4d6a08", border: `1px solid ${R}33` }}>
          <span className="font-mono text-sm" style={{ color: "#fca5a5" }}>{err}</span>
          <button onClick={runRecommendation}
            className="ml-auto px-3 py-1 font-mono text-xs font-bold text-black rounded"
            style={{ background: G }}>
            Generate First Report
          </button>
        </div>
      )}

      <div className="max-w-screen-2xl mx-auto px-6 py-6 space-y-5">

        {/* ── Chart Carousel on Main Dashboard ── */}
        {tab === "portfolio" && report && (
          <div className="panel p-5 flex flex-col justify-between animate-fade-in-up" style={{ minHeight: "440px" }}>
            <div className="flex flex-wrap items-center justify-between gap-4 mb-4 pb-3" style={{ borderBottom: `1px solid ${DIM}` }}>
              <div className="flex items-center gap-3">
                <span className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>
                  ◈ Dynamic Chart Carousel
                </span>
                {activeCarouselTicker && (
                  <span className="font-mono text-xs font-bold px-2.5 py-1 rounded bg-[#00d97e]/10 text-[#00d97e] border border-[#00d97e]/20 uppercase animate-pulse">
                    {fmt.tick(activeCarouselTicker)}
                  </span>
                )}
              </div>
            </div>

            {/* Ticker Selector Pills */}
            <div className="flex flex-wrap gap-1.5 mb-4">
              {allocatedTickers.map((t, idx) => (
                <button
                  key={t}
                  onClick={() => {
                    setCarouselIndex(idx);
                  }}
                  className="font-mono text-[10px] px-2.5 py-1 rounded-md transition-all"
                  style={{
                    background: idx === carouselIndex ? "#00d97e" : "#111827",
                    color: idx === carouselIndex ? "#000" : "#64748b",
                    border: `1px solid ${idx === carouselIndex ? "#00d97e" : "transparent"}`
                  }}
                >
                  {fmt.tick(t)}
                </button>
              ))}
            </div>

            {/* Dynamic Candle Chart */}
            <div className="flex-1 rounded-lg overflow-hidden border border-slate-900 bg-[#070a0f] relative" style={{ height: "300px" }}>
              <div 
                className={`w-full h-full transition-all duration-300 ease-in-out transform ${
                  fadeState === "out" ? "opacity-0 translate-x-4" : "opacity-100 translate-x-0"
                }`}
              >
                {activeCarouselTicker ? (
                  <CandleChartDynamic
                    chartId="portfolio-carousel-candle"
                    symbol={activeCarouselTicker}
                    timeframe="1d"
                    bucketSize={0.05}
                    multiplier={100}
                    chartType="candlestick"
                    showVolumeProfile={false}
                    isActive={true}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-xs text-slate-500 font-mono">
                    No active holdings to display
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── KPI Strip ─────────────────────────────────────── */}
        {["portfolio", "advisor"].includes(tab) && report && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 animate-fade-in-up">
            <KPI
              label="Expected Return"
              value={fmt.pct(report.expected_return ?? 0)}
              color={(report.expected_return ?? 0) >= 0 ? G : R}
            />
            <KPI
              label="LLM Confidence"
              value={fmt.conf(report.llm_confidence ?? 0)}
              color={G}
              sub={report.source ?? ""}
            />
            <KPI
              label="Active Holdings"
              value={`${allocations.filter(([, w]) => w >= 0.01).length}`}
              sub={`of ${allocations.length} tickers`}
            />
            <KPI
              label="India VIX"
              value={vix.vix > 0 ? vix.vix.toFixed(2) : "—"}
              color={vix.status === "fear" ? R : vix.status === "caution" ? "#f59e0b" : G}
              sub={vix.status.toUpperCase()}
            />
            <KPI
              label="AI Regime"
              value={regimeLabel(report.regime)}
              color={regimeColor(report.regime)}
              sub={`probs: ${Object.entries(report.regime_probs ?? {})
                .sort(([, a], [, b]) => b - a)
                .slice(0, 2)
                .map(([k, v]) => `${regimeLabel(k)} ${(v * 100).toFixed(0)}%`)
                .join(" · ")}`}
            />
          </div>
        )}

        {/* ── AI Advisor Panel on Main Dashboard ── */}
        {tab === "portfolio" && report && (
          <div className="panel p-5 animate-fade-in-up space-y-4" style={{ borderColor: `${G}22` }}>
            <div className="font-mono text-[11px] font-bold uppercase tracking-widest text-[#64748b] border-b pb-3" style={{ borderColor: `${DIM}33` }}>
              ✦ Cognitive AI Advisor
            </div>
            
            {report.reasoning ? (
              <div className="space-y-4">
                {/* AI Reasoning Text */}
                <div className="p-4 rounded-xl space-y-2 bg-[#0d1117]/80 border" style={{ borderColor: `${DIM}88` }}>
                  <div className="font-mono text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    AI Reasoning & Regime Synthesis
                  </div>
                  <p className="text-xs leading-relaxed text-slate-300 font-mono whitespace-pre-line">{report.reasoning}</p>
                </div>

                {/* Risk Warnings */}
                {report.risk_flags && report.risk_flags.length > 0 && (
                  <div className="p-4 rounded-xl space-y-2 bg-[#ff4d6a]/5 border" style={{ borderColor: `${R}33` }}>
                    <div className="font-mono text-[10px] font-bold uppercase tracking-widest" style={{ color: R }}>
                      ⚠️ Risk Warnings
                    </div>
                    <div className="space-y-1">
                      {report.risk_flags.map((f, i) => (
                        <div key={i} className="font-mono text-xs flex items-start gap-2" style={{ color: "#fca5a5" }}>
                          <span style={{ color: R }}>▸</span>{f}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Memory Citations */}
                {report.memory_citations && report.memory_citations.length > 0 && (
                  <div className="space-y-2.5">
                    <div className="font-mono text-[10px] font-bold uppercase tracking-widest text-slate-400">
                      ⬡ Episodic Memory Citations (Qdrant Retrieval)
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {report.memory_citations.map((c, i) => (
                        <div key={i} className="p-3.5 rounded-xl space-y-1.5 bg-[#0d1117]/60 border" style={{ borderColor: `${DIM}66` }}>
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs font-bold" style={{ color: "#14b8a6" }}>{c.date}</span>
                            <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20">{typeof c.similarity === 'number' ? `${(c.similarity * 100).toFixed(1)}% match` : c.similarity}</span>
                          </div>
                          {c.outcome && <p className="font-mono text-[11px] leading-relaxed text-slate-400">{c.outcome}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 font-mono text-xs text-slate-500 italic">
                No reasoning report available.
              </div>
            )}
          </div>
        )}

        {/* ── Dynamic Universe Configurator ── */}
        {tab === "portfolio" && (
          <div className="panel p-5 accent-glow transition-all duration-300" style={{ borderColor: `${G}22` }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => { logClick("Toggle Universe Customizer", { opening: !showCustomizer }); setShowCustomizer(!showCustomizer); }}
          >
            <div className="flex items-center gap-2.5">
              <span className="font-mono text-xs font-bold" style={{ color: G }}>PORTFOLIO UNIVERSE CUSTOMIZER</span>
              <span className="text-[11px] text-slate-500 font-mono">({customTickers.length} active stocks · start: {startYear})</span>
            </div>
            <button className="font-mono text-xs text-slate-400 hover:text-white focus:outline-none">
              {showCustomizer ? "Collapse [−]" : "Expand [+]"}
            </button>
          </div>

          {/* Always-visible selected-ticker strip */}
          {!showCustomizer && customTickers.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5 max-h-[88px] overflow-y-auto">
              {customTickers.map((t) => (
                <span
                  key={t}
                  className="font-mono text-[10px] px-2 py-0.5 rounded border flex items-center gap-1"
                  style={{ background: `${G}0c`, borderColor: `${G}44`, color: "#94a3b8" }}
                >
                  {t.replace(".NS", "")}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); logClick("Remove Ticker (strip)", { ticker: t }); setCustomTickers(customTickers.filter((x) => x !== t)); }}
                    className="text-red-500 hover:text-red-400 font-bold leading-none focus:outline-none"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          
          {showCustomizer && (
            <div className="mt-5 space-y-4 border-t pt-4" style={{ borderColor: `${DIM}33` }}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Left: Tickers list */}
                <div className="space-y-2">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-[#64748b] block">Active Tickers ({customTickers.length})</label>
                  <div className="flex flex-wrap gap-2 p-3 rounded min-h-[80px]" style={{ background: "#111827", border: `1px solid ${DIM}` }}>
                    {customTickers.map((t, idx) => (
                      <span key={idx} className="font-mono text-xs px-2.5 py-1 rounded bg-[#070a0f] text-slate-300 flex items-center gap-1.5 border border-[#1e2d40]">
                        {fmt.tick(t)}
                        <button 
                          onClick={() => { logClick("Remove Ticker (list)", { ticker: t }); setCustomTickers(customTickers.filter(x => x !== t)); }}
                          className="text-red-500 hover:text-red-400 font-bold ml-1 focus:outline-none"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    {customTickers.length === 0 && (
                      <span className="text-xs text-slate-500 font-mono">No stocks added. Add below.</span>
                    )}
                  </div>
                </div>

                {/* Right: Add stock & Start year */}
                <div className="space-y-4">
                  <div className="flex gap-2">
                    <div className="flex-1 relative">
                      <label className="text-[10px] font-mono uppercase tracking-widest text-[#64748b] block mb-1">Add Stock (NSE Symbol)</label>
                      <input 
                        type="text" 
                        value={newTickerInput}
                        onChange={e => setNewTickerInput(e.target.value.toUpperCase())}
                        placeholder="Search name or ticker..."
                        className="w-full font-mono text-xs px-3 py-2.5 rounded outline-none"
                        style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                        onKeyDown={e => {
                          if (e.key === "Enter") {
                            const val = newTickerInput.trim().toUpperCase();
                            if (val) {
                              const cleanTicker = val.includes(".") ? val : `${val}.NS`;
                              logClick("Add Ticker (manual input - Enter)", { ticker: cleanTicker });
                              if (!customTickers.includes(cleanTicker)) {
                                setCustomTickers([...customTickers, cleanTicker]);
                              }
                              setNewTickerInput("");
                            }
                          }
                        }}
                      />
                      
                      {/* Autocomplete Dropdown overlay for dashboard customizer */}
                      {newTickerInput.trim().length >= 2 && (() => {
                        const query = newTickerInput.toLowerCase().trim();
                        const matches = (nifty500Data as { ticker: string; name: string }[])
                          .filter(s => s.name.toLowerCase().includes(query) || s.ticker.toLowerCase().includes(query))
                          .slice(0, 8);
                        
                        const showForceAdd = query.length >= 2 && !matches.some(s => s.ticker.toLowerCase() === query || s.ticker.toLowerCase().replace(".ns","") === query);
                        
                        if (matches.length > 0 || showForceAdd) {
                          return (
                            <div className="absolute left-0 right-0 mt-1 rounded-lg shadow-2xl border z-50 overflow-hidden"
                              style={{ background: "#0d1117", borderColor: DIM }}>
                              {matches.map(stock => {
                                const alreadyAdded = customTickers.includes(stock.ticker);
                                return (
                                  <button
                                    key={stock.ticker}
                                    type="button"
                                    onClick={() => {
                                      if (!alreadyAdded) {
                                        logClick("Add Ticker (autocomplete)", { ticker: stock.ticker, name: stock.name });
                                        setCustomTickers([...customTickers, stock.ticker]);
                                      }
                                      setNewTickerInput("");
                                    }}
                                    className="w-full text-left px-4 py-2 hover:bg-[#00d97e]/10 text-[11px] font-mono flex items-center justify-between transition-colors border-b last:border-b-0"
                                    style={{ borderColor: `${DIM}33` }}
                                  >
                                    <span className="text-white truncate mr-2" style={{ color: alreadyAdded ? "#64748b" : "white" }}>
                                      {stock.name} {alreadyAdded && "✓"}
                                    </span>
                                    <span className="text-[#00d97e] font-bold shrink-0">
                                      {stock.ticker.replace(".NS", "")}
                                    </span>
                                  </button>
                                );
                              })}
                              
                              {showForceAdd && (() => {
                                const cleanTicker = query.toUpperCase().includes(".") ? query.toUpperCase() : `${query.toUpperCase()}.NS`;
                                const alreadyAdded = customTickers.includes(cleanTicker);
                                return (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!alreadyAdded) {
                                        logClick("Force-Add Ticker", { ticker: cleanTicker });
                                        setCustomTickers([...customTickers, cleanTicker]);
                                      }
                                      setNewTickerInput("");
                                    }}
                                    className="w-full text-left px-4 py-2 hover:bg-[#00d97e]/10 text-[11px] font-mono flex items-center justify-between transition-colors border-t border-dashed"
                                    style={{ borderColor: `${DIM}55` }}
                                  >
                                    <span className="text-yellow-500 font-bold">
                                      + Force Add {alreadyAdded && "✓"}
                                    </span>
                                    <span className="text-[#00d97e] font-bold shrink-0">
                                      {cleanTicker}
                                    </span>
                                  </button>
                                );
                              })()}
                            </div>
                          );
                        }
                        return null;
                      })()}
                    </div>
                    <button 
                      onClick={() => {
                        const val = newTickerInput.trim().toUpperCase();
                        if (val) {
                          const cleanTicker = val.includes(".") ? val : `${val}.NS`;
                          logClick("Add Ticker (manual input)", { ticker: cleanTicker });
                          if (!customTickers.includes(cleanTicker)) {
                            setCustomTickers([...customTickers, cleanTicker]);
                          }
                          setNewTickerInput("");
                        }
                      }}
                      className="px-4 py-2 mt-5 text-xs font-mono font-bold text-black rounded self-end focus:outline-none shrink-0"
                      style={{ background: G }}
                    >
                      Add
                    </button>
                  </div>

                  <div>
                    <label className="text-[10px] font-mono uppercase tracking-widest text-[#64748b] block mb-1">Historical Window Start Year</label>
                    <select
                      value={startYear}
                      onChange={e => {
                        logConfig("startYear", e.target.value);
                        setStartYear(e.target.value);
                      }}
                      className="w-full font-mono text-xs px-3 py-2 rounded outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                    >
                      {["2018", "2019", "2020", "2021", "2022", "2023", "2024"].map(yr => (
                        <option key={yr} value={yr}>{yr} (provides {new Date().getFullYear() - parseInt(yr)}y+ history)</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t pt-4" style={{ borderColor: `${DIM}33` }}>
                <button 
                  onClick={() => {
                    logClick("Reset Defaults");
                    setCustomTickers(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS"]);
                    setStartYear("2022");
                  }}
                  className="px-3 py-1.5 text-xs font-mono font-bold rounded transition-colors focus:outline-none"
                  style={{ background: "#111827", color: "#64748b", border: `1px solid ${DIM}` }}
                >
                  Reset Defaults
                </button>
                <button 
                  onClick={runRecommendation}
                  disabled={recLoading}
                  className="px-4 py-1.5 text-xs font-mono font-bold text-black rounded transition-all hover:opacity-90 disabled:opacity-50 focus:outline-none"
                  style={{ background: G }}
                >
                  Build Fresh SAC Portfolio
                </button>
              </div>
            </div>
          )}
        </div>
        )}

        {/* ── Portfolio Tab ──────────────────────────────────── */}
        {tab === "advisor" && report && (
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-5 animate-fade-in-up">
            {/* Allocation table */}
            <div className="xl:col-span-3 panel overflow-hidden">
              <div className="px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-widest"
                style={{ color: "#64748b", borderBottom: `1px solid ${DIM}` }}>
                DhanNiti V2 SAC Allocations — {fmt.date(report.date ?? report.as_of ?? "")}
              </div>
              {/* Stacked allocation bar */}
              <div className="px-5 py-3" style={{ borderBottom: `1px solid ${DIM}` }}>
                <div className="flex h-5 rounded-full overflow-hidden gap-px">
                  {allocations.map(([ticker, weight]) => (
                    <div
                      key={ticker}
                      title={`${fmt.tick(ticker)}: ${fmt.pct(weight)}`}
                      style={{
                        width: `${weight * 100}%`,
                        background: ticker === selectedTicker ? G : `${G}55`,
                        transition: "all 0.3s",
                      }}
                    />
                  ))}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                  {allocations.filter(([, w]) => w > 0.01).map(([ticker, weight]) => (
                    <span key={ticker} className="font-mono text-[10px]" style={{ color: "#64748b" }}>
                      <span style={{ color: G }}>▊</span> {fmt.tick(ticker)} {fmt.pct(weight)}
                    </span>
                  ))}
                </div>
              </div>
              {/* Table */}
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${DIM}` }}>
                    {["Ticker", "SAC Weight", "XGB Signal", "XGB Conf", "Note"].map(h => (
                      <th key={h} className="px-5 py-3 text-left font-mono text-[10px] uppercase tracking-wider"
                        style={{ color: "#374151" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {allocations.map(([ticker, weight]) => {
                    const bd = breakdownMap[ticker];
                    const xgbSignal = bd?.xgb_signal ?? bd?.action ?? "—";
                    const xgbConf = bd?.xgb_confidence ?? bd?.confidence ?? 0;
                    const note = bd?.note ?? bd?.llm_note ?? "";
                    const isBull = xgbSignal?.toLowerCase().includes("bull") ||
                                   xgbSignal?.toLowerCase() === "buy";
                    return (
                      <tr
                        key={ticker}
                        className="cursor-pointer transition-colors hover:bg-[#111827]"
                        style={{
                          borderBottom: `1px solid ${DIM}11`,
                          background: selectedTicker === ticker ? "#111827" : undefined,
                        }}
                        onClick={() => {
                          logTickerSelect(ticker, "portfolio allocation table");
                          logNav("signals", tab);
                          setSelectedTicker(ticker);
                          setTab("signals");
                        }}
                      >
                        <td className="px-5 py-3 font-mono font-bold text-white">
                          {fmt.tick(ticker)}
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold" style={{ color: G }}>{fmt.pct(weight)}</span>
                            <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: "#1e2d40" }}>
                              <div className="h-full rounded-full" style={{ width: `${weight * 100 / 0.30 * 100}%`, background: G }} />
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded uppercase"
                            style={{
                              color: isBull ? G : "#ff4d6a",
                              background: isBull ? `${G}18` : "#ff4d6a18",
                              border: `1px solid ${isBull ? G : "#ff4d6a"}33`,
                            }}>
                            {isBull ? "▲ " : "▼ "}{xgbSignal}
                          </span>
                        </td>
                        <td className="px-5 py-3 font-mono text-[11px]" style={{ color: "#94a3b8" }}>
                          {typeof xgbConf === "number" ? fmt.conf(xgbConf) : "—"}
                        </td>
                        <td className="px-5 py-3 text-xs max-w-xs" style={{ color: "#64748b" }}>
                          {note ? <span className="line-clamp-2">{note}</span> : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Right column */}
            <div className="xl:col-span-2 space-y-5">
              {/* Weight bar chart */}
              <div className="panel p-5">
                <div className="font-mono text-[11px] font-bold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
                  Weight Distribution
                </div>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={allocations.map(([ticker, weight]) => ({ ticker, weight }))}
                    layout="vertical" margin={{ left: 50, right: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={DIM} />
                    <XAxis type="number" tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                      tick={{ fill: "#374151", fontSize: 11, fontFamily: "JetBrains Mono" }} axisLine={false} />
                    <YAxis dataKey="ticker" type="category" axisLine={false} tickLine={false}
                      tick={{ fill: "#94a3b8", fontSize: 11, fontFamily: "JetBrains Mono" }}
                      tickFormatter={fmt.tick} />
                    <Tooltip
                      contentStyle={{ background: "#0d1117", border: `1px solid ${DIM}`, borderRadius: 8, fontFamily: "JetBrains Mono", fontSize: 12 }}
                      formatter={(v) => fmt.pct(Number(v ?? 0))}
                    />
                    <Bar dataKey="weight" radius={[0, 4, 4, 0]} maxBarSize={20} fill={G} fillOpacity={0.8} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Rebalance cost simulator */}
              <div className="panel p-5 accent-glow flex flex-col justify-between" style={{ borderColor: `${G}33`, minHeight: "180px" }}>
                <div>
                  <div className="font-mono text-[11px] font-bold uppercase tracking-widest mb-2" style={{ color: "#64748b" }}>
                    Rebalance Cost Simulator
                  </div>
                  <p className="text-[11px] mb-3" style={{ color: "#94a3b8" }}>
                    Estimates STT + brokerage to execute SAC weights from equal-weight.
                  </p>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="font-mono text-[11px]" style={{ color: "#64748b" }}>₹</span>
                    <input
                      type="number"
                      value={portfolioValue}
                      onChange={e => {
                        const val = Number(e.target.value);
                        logConfig("portfolioValue", val);
                        setPortfolioValue(val);
                      }}
                      className="flex-1 font-mono text-sm px-3 py-1.5 rounded outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                      min={100000} step={100000}
                    />
                  </div>
                </div>
                {simCost !== null ? (
                  <div className="flex items-center justify-between p-3 rounded"
                    style={{ background: "#111827", border: `1px solid ${DIM}` }}>
                    <span className="font-mono text-xs" style={{ color: "#94a3b8" }}>Est. Rebalance Cost</span>
                    <span className="font-mono text-lg font-bold" style={{ color: R }}>₹{simCost.toLocaleString("en-IN")}</span>
                  </div>
                ) : (
                  <button onClick={runSimulation}
                    className="w-full px-3 py-2 text-xs font-mono font-bold rounded transition-colors"
                    style={{ background: "#111827", color: G, border: `1px dashed ${G}55` }}>
                    ⚡ SIMULATE COSTS
                  </button>
                )}
              </div>
            </div>
          </div>
        )}


        {/* ── Signals Tab ────────────────────────────────────── */}
        {tab === "signals" && (
          <div className="space-y-5 animate-fade-in-up">

            {/* ── Row 0: Header + Ticker Picker ── */}
            <div className="panel" style={{ borderColor: `${G}22` }}>
              <div className="px-5 py-3 flex flex-wrap items-center justify-between gap-3"
                style={{ borderBottom: `1px solid ${DIM}` }}>
                <div className="flex items-center gap-3">
                  <div>
                    <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>Chart Workspace</div>
                    <div className="font-mono text-xs text-white">{selectedTicker ? fmt.tick(selectedTicker) : "Select a ticker below"}</div>
                  </div>
                </div>
                {/* Symbol Search — unified search for NSE Equities & Futures */}
                <div className="flex items-center gap-3">
                  <SymbolSearchDynamic
                    onSelectSymbol={(sym) => {
                      // Convert Fyers symbol back to YF-style for state (or keep as-is)
                      setSelectedTicker(sym);
                    }}
                    currentSymbol={selectedTicker ? mapYfToFyers(selectedTicker) : undefined}
                  />
                  <span className="font-mono text-[9px] text-slate-600 whitespace-nowrap">NSE Eq · Fut</span>
                </div>
              </div>

              {/* Ticker quick-pick row */}
              <div className="p-4 flex gap-2 flex-wrap">
                {((report?.tickers?.length ? report.tickers : customTickers)).map(t => (
                  <button key={t} onClick={() => { logTickerSelect(t, "signals tab button"); setSelectedTicker(t); }}
                    className="font-mono text-xs px-3 py-1 rounded transition-all"
                    style={{
                      background: selectedTicker === t ? G : "#111827",
                      color: selectedTicker === t ? "#000" : "#64748b",
                      border: `1px solid ${selectedTicker === t ? G : DIM}`
                    }}>
                    {fmt.tick(t)}
                  </button>
                ))}
                {!report?.tickers?.length && (
                  <span className="font-mono text-[10px] text-slate-600 italic self-center">
                    Showing custom universe · run pipeline to get allocations
                  </span>
                )}
              </div>
            </div>

            {selectedTicker && (
              <>
                {/* Ticker Signal KPIs */}
                {report && (() => {
                  const bd = breakdownMap[selectedTicker];
                  const w = report.sac_allocations?.[selectedTicker] ?? report.ppo_allocations?.[selectedTicker] ?? report.allocations?.[selectedTicker] ?? 0;
                  return bd ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <KPI label="SAC Weight" value={fmt.pct(w)} color={G} />
                      <KPI label="XGB Signal" value={(bd.xgb_signal ?? bd.action ?? "—").toUpperCase()} />
                      <KPI label="XGB Confidence" value={fmt.conf(bd.xgb_confidence ?? bd.confidence ?? 0)} />
                      <KPI label="Weight ×₹10L" value={fmt.inr(w * 1000000)} />
                    </div>
                  ) : null;
                })()}

                {/* ── Panel 1: Candlestick Chart ── */}
                <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                  <div className="flex items-center gap-3 px-5 py-3" style={{ borderBottom: `1px solid ${DIM}`, background: "#070a0f" }}>
                    <div>
                      <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>Candlestick Chart</div>
                      <div className="font-mono text-[10px]" style={{ color: "#374151" }}>OHLCV · Volume Profile overlay</div>
                    </div>
                    
                    {/* Toolbar */}
                    <div className="ml-auto flex items-center gap-3">
                      <div className="flex items-center gap-1 bg-[#111827] rounded p-0.5 border border-[#1e2d40]">
                        {['1m', '5m', '15m', '1h', '1d'].map(tf => (
                          <button 
                            key={tf}
                            onClick={() => setCandleTimeframe(tf)}
                            className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${candleTimeframe === tf ? 'bg-[#3b82f6] text-white' : 'text-[#64748b] hover:text-[#e2e8f0]'}`}
                          >
                            {tf.toUpperCase()}
                          </button>
                        ))}
                      </div>
                      
                      <div className="flex items-center gap-1 bg-[#111827] rounded p-0.5 border border-[#1e2d40]">
                        {['SMA', 'EMA', 'VWAP', 'BB'].map(ind => (
                          <button 
                            key={ind}
                            onClick={() => toggleIndicator(ind)}
                            className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${candleIndicators.includes(ind) ? 'bg-[#00d97e] text-black' : 'text-[#64748b] hover:text-[#e2e8f0]'}`}
                          >
                            {ind}
                          </button>
                        ))}
                      </div>

                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold ml-2" style={{ background: `${G}18`, color: G, border: `1px solid ${G}33` }}>LIVE</span>
                    </div>
                  </div>
                  <div style={{ height: "480px" }}>
                    <CandleChartDynamic
                      chartId="signals-candle"
                      symbol={selectedTicker}
                      timeframe={candleTimeframe}
                      bucketSize={0.05}
                      multiplier={100}
                      chartType="candlestick"
                      showVolumeProfile={true}
                      indicators={candleIndicators}
                      isActive={true}
                      onBookUpdate={setBookData}
                    />
                  </div>
                </div>

                {/* ── Panel 2: Footprint / Orderflow Chart ── */}
                <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                  <div className="flex items-center gap-3 px-5 py-3" style={{ borderBottom: `1px solid ${DIM}`, background: "#070a0f" }}>
                    <div>
                      <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>Orderflow / Footprint Chart</div>
                      <div className="font-mono text-[10px]" style={{ color: "#374151" }}>Buy/Sell volume cells per candle · Delta imbalance · Aggressor flow</div>
                    </div>
                    <div className="ml-auto flex items-center gap-3">
                      <div className="flex items-center gap-1 bg-[#111827] rounded p-0.5 border border-[#1e2d40]">
                        {['1m', '5m', '15m'].map(tf => (
                          <button 
                            key={tf}
                            onClick={() => setFootprintTimeframe(tf)}
                            className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${footprintTimeframe === tf ? 'bg-[#8b5cf6] text-white' : 'text-[#64748b] hover:text-[#e2e8f0]'}`}
                          >
                            {tf.toUpperCase()}
                          </button>
                        ))}
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold" style={{ background: "#8b5cf622", color: "#a78bfa", border: "1px solid #8b5cf633" }}>FOOTPRINT</span>
                    </div>
                  </div>
                  <div style={{ height: "480px" }}>
                    <CandleChartDynamic
                      chartId="signals-footprint"
                      symbol={selectedTicker}
                      timeframe={footprintTimeframe}
                      bucketSize={0.05}
                      multiplier={100}
                      chartType="footprint"
                      showVolumeProfile={false}
                      isActive={false}
                    />
                  </div>
                </div>

                {/* ── Panel 3: Volume Profile + DOM — side by side ── */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

                  {/* Volume Profile */}
                  <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                    <div className="flex items-center gap-3 px-5 py-3" style={{ borderBottom: `1px solid ${DIM}`, background: "#070a0f" }}>
                      <div>
                        <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>Volume Profile</div>
                        <div className="font-mono text-[10px]" style={{ color: "#374151" }}>Session histogram · POC · Value Area (70%)</div>
                      </div>
                      <div className="ml-auto flex items-center gap-3">
                        <div className="flex items-center gap-1 bg-[#111827] rounded p-0.5 border border-[#1e2d40]">
                          {['5m', '15m', '1h', '1d'].map(tf => (
                            <button 
                              key={tf}
                              onClick={() => setVpTimeframe(tf)}
                              className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${vpTimeframe === tf ? 'bg-[#f59e0b] text-white' : 'text-[#64748b] hover:text-[#e2e8f0]'}`}
                            >
                              {tf.toUpperCase()}
                            </button>
                          ))}
                        </div>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold" style={{ background: "#f59e0b22", color: "#f59e0b", border: "1px solid #f59e0b33" }}>VP</span>
                      </div>
                    </div>
                    <div style={{ height: "420px" }}>
                      <CandleChartDynamic
                        chartId="signals-volprofile"
                        symbol={selectedTicker}
                        timeframe={vpTimeframe}
                        bucketSize={0.05}
                        multiplier={100}
                        chartType="candlestick"
                        showVolumeProfile={true}
                        isActive={false}
                      />
                    </div>
                  </div>

                  {/* Depth of Market (DOM) */}
                  <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                    <div className="flex items-center gap-3 px-5 py-3" style={{ borderBottom: `1px solid ${DIM}`, background: "#070a0f" }}>
                      <div>
                        <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>Depth of Market — DOM</div>
                        <div className="font-mono text-[10px]" style={{ color: "#374151" }}>50-level L2 bid/ask order book · Imbalance · Sentiment</div>
                      </div>
                      <div className="ml-auto">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold" style={{ background: "#14b8a622", color: "#2dd4bf", border: "1px solid #14b8a633" }}>L2</span>
                      </div>
                    </div>
                    <div style={{ height: "420px" }}>
                      <DomPanelDynamic
                        symbol={mapYfToFyers(selectedTicker)}
                        ltp={bookData?.ltp || 0}
                        bids={bookData?.bids || []}
                        asks={bookData?.asks || []}
                        tbq={bookData?.tot_buy_qty || 0}
                        tsq={bookData?.tot_sell_qty || 0}
                        sentiment={bookData?.sentiment || 0}
                        imbalance_50={bookData?.imbalance_50 || 0}
                      />
                    </div>
                  </div>
                </div>

                {/* ── Panel 5: Stock Screener ── */}
                <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                  <div style={{ height: "300px" }}>
                    <StockScreenerDynamic 
                      onSelectSymbol={(sym) => {
                        setSelectedTicker(sym);
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                      }}
                    />
                  </div>
                </div>

                {/* ── Panel 6: News + Sentiment ── */}
                <div className="panel overflow-hidden" style={{ borderColor: "#1e2d40" }}>
                  <div className="flex items-center gap-3 px-5 py-3" style={{ borderBottom: `1px solid ${DIM}`, background: "#070a0f" }}>
                    <span className="text-base">📰</span>
                    <div>
                      <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>FinBERT Sentiment + Live Catalysts</div>
                      <div className="font-mono text-[10px]" style={{ color: "#374151" }}>Real-time news scoring · Positive / Neutral / Negative</div>
                    </div>
                  </div>
                  <div className="relative grid grid-cols-1 md:grid-cols-3 gap-4 p-5">
                    <div className="p-4 rounded-lg" style={{ background: "#070a0f", border: `1px solid ${DIM}` }}>
                      <div className="font-mono text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Composite Score</div>
                      {news ? (
                        <div className="space-y-3">
                          <div className="flex justify-between">
                            <span className="text-xs" style={{ color: "#94a3b8" }}>Score</span>
                            <span className="font-mono text-sm font-bold"
                              style={{ color: news.sentiment.composite >= 0 ? G : R }}>
                              {news.sentiment.composite >= 0 ? "+" : ""}{news.sentiment.composite.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex gap-2 text-[10px] font-mono flex-wrap">
                            <span className="px-2 py-0.5 rounded" style={{ background: `${G}22`, color: G }}>▲ {Math.round(news.sentiment.positive * 100)}%</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: "#37415133", color: "#94a3b8" }}>— {Math.round(news.sentiment.neutral * 100)}%</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: `${R}22`, color: R }}>▼ {Math.round(news.sentiment.negative * 100)}%</span>
                          </div>
                        </div>
                      ) : newsLoading ? (
                        <div className="text-xs font-mono animate-pulse" style={{ color: "#64748b" }}>Scoring...</div>
                      ) : (
                        <div className="text-xs font-mono" style={{ color: "#374151" }}>No data yet.</div>
                      )}
                    </div>

                    <div className="p-4 rounded-lg md:col-span-2" style={{ background: "#070a0f", border: `1px solid ${DIM}` }}>
                      <div className="font-mono text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Live Catalyst Feed</div>
                      {newsLoading ? (
                        <div className="text-xs font-mono animate-pulse" style={{ color: "#64748b" }}>Fetching news...</div>
                      ) : news?.headlines.length ? (
                        <div className="space-y-2 max-h-[160px] overflow-y-auto pr-2">
                          {news.headlines.map((h, i) => (
                            <div key={i} className="text-xs flex items-start gap-2 py-1"
                              style={{ borderBottom: i < news.headlines.length - 1 ? `1px solid ${DIM}22` : "none", color: "#94a3b8" }}>
                              <span style={{ color: G }}>⚡</span>
                              <span className="line-clamp-2">{h}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs font-mono" style={{ color: "#374151" }}>No live catalysts found.</div>
                      )}
                    </div>

                    {isUsingFallback && (
                      <div className="absolute inset-0 bg-[#070a0f]/85 backdrop-blur-sm flex flex-col items-center justify-center text-center p-4 z-10 rounded border border-yellow-500/10">
                        <span className="text-yellow-400 text-xs mb-1 font-mono font-bold">News Feed Offline</span>
                        <span className="text-[11px] text-slate-400 max-w-xs font-mono">Requires local FastAPI server.</span>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── No allocations message ── */}
        {tab === "advisor" && !report && (
          <div className="panel p-12 text-center font-mono text-sm" style={{ color: "#374151" }}>
            No recommended allocations yet. Click RUN PIPELINE to generate them.
          </div>
        )}

        {/* ── Breakdown Tab ──────────────────────────────────── */}
        {tab === "breakdown" && report && (
          <div className="panel animate-fade-in-up">
            <div className="px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-widest"
              style={{ color: "#64748b", borderBottom: `1px solid ${DIM}` }}>
              Stock Breakdown — XGBoost · SAC · Groq per-ticker
            </div>
            <div className="p-5 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {allocations.map(([ticker, weight]) => {
                const bd = breakdownMap[ticker];
                const signal = bd?.xgb_signal ?? bd?.action ?? "neutral";
                const conf = bd?.xgb_confidence ?? bd?.confidence ?? 0;
                const note = bd?.note ?? bd?.llm_note ?? "";
                const isBull = signal.toLowerCase().includes("bull") || signal.toLowerCase() === "buy";
                return (
                  <div
                    key={ticker}
                    className="panel p-4 space-y-3 cursor-pointer transition-all"
                    style={{ borderColor: selectedTicker === ticker ? `${G}55` : DIM }}
                    onClick={() => {
                      logTickerSelect(ticker, "breakdown card click");
                      logNav("signals", tab);
                      setSelectedTicker(ticker);
                      setTab("signals");
                    }}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-mono font-bold text-white text-base">{fmt.tick(ticker)}</div>
                        <div className="font-mono text-[11px] font-bold" style={{ color: G }}>
                          {fmt.pct(weight)} SAC weight
                        </div>
                      </div>
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded uppercase"
                        style={{
                          color: isBull ? G : R,
                          background: isBull ? `${G}18` : `${R}18`,
                          border: `1px solid ${isBull ? G : R}33`,
                        }}>
                        {isBull ? "▲" : "▼"} {signal}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: "#1e2d40" }}>
                        <div className="h-full rounded-full" style={{ width: `${conf * 100}%`, background: isBull ? G : R }} />
                      </div>
                      <span className="font-mono text-[10px]" style={{ color: "#64748b" }}>
                        conf {fmt.conf(conf)}
                      </span>
                    </div>
                    {note && (
                      <p className="text-[11px] leading-relaxed line-clamp-3" style={{ color: "#64748b" }}>{note}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Progression Tab ────────────────────────────────────── */}
        {tab === "progression" && (
          <div className="space-y-6 animate-fade-in-up">
            {/* Machine Learning Workflow Card */}
            <div className="panel border border-slate-800 rounded-lg overflow-hidden bg-[#0d141f]">
              <div className="px-5 py-4 font-mono text-[11px] font-bold uppercase tracking-widest flex items-center justify-between"
                style={{ color: "#64748b", borderBottom: `1px solid ${DIM}`, background: '#090f17' }}>
                <span>Machine Learning Workflow (SAC RL Engine)</span>
                <span className="text-[10px] text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded">strictly sac-based</span>
              </div>
              <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* STATE SPACE */}
                <div className="p-5 rounded-lg bg-[#080d14] border border-slate-800/80 flex flex-col justify-between space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">STATE SPACE (OBSERVATIONS)</span>
                    </div>
                    <h3 className="text-lg font-mono font-bold text-white mb-2">Asset & Regime States</h3>
                    <p className="text-xs text-slate-400 leading-relaxed font-mono mb-4">
                      At each step <span className="text-emerald-400">t</span>, the SAC agent receives a multi-dimensional state vector mapping the market environment:
                    </p>
                    <ul className="text-xs text-slate-400 font-mono space-y-2.5 list-disc pl-4 leading-relaxed">
                      <li><strong className="text-slate-300">Price Momentum & Volatility:</strong> 14d ATR, Bollinger Bands, and rolling standard deviations.</li>
                      <li><strong className="text-slate-300">Market Regimes:</strong> India VIX and GMM/HMM-detected state shifts.</li>
                      <li><strong className="text-slate-300">Alternative Alt-Data:</strong> FinBERT sentiment scores parsing daily Indian equity news feeds.</li>
                      <li><strong className="text-slate-300">Portfolio State:</strong> The current weights vector <span className="text-slate-300">w_t-1</span>.</li>
                    </ul>
                  </div>
                </div>

                {/* ACTION SPACE */}
                <div className="p-5 rounded-lg bg-[#080d14] border border-slate-800/80 flex flex-col justify-between space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">ACTION SPACE (POLICY)</span>
                    </div>
                    <h3 className="text-lg font-mono font-bold text-white mb-2">Continuous Weight Control</h3>
                    <p className="text-xs text-slate-400 leading-relaxed font-mono mb-4">
                      DhanNiti uses a continuous policy network outputting optimal asset weight offsets:
                    </p>
                    <ul className="text-xs text-slate-400 font-mono space-y-2.5 list-disc pl-4 leading-relaxed">
                      <li><strong className="text-slate-300">Bounded Allocations:</strong> Bounded strictly between <span className="text-emerald-400">2%</span> and <span className="text-emerald-400">35%</span> per stock to avoid over-concentration risks.</li>
                      <li><strong className="text-slate-300">Cash Buffer:</strong> Dynamic allocations to cash-equivalents (Liquid BeES) when regime volatility rises.</li>
                      <li><strong className="text-slate-300">Dirichlet/Softmax Layer:</strong> Ensures all weights strictly sum to <span className="text-emerald-400">100%</span>.</li>
                    </ul>
                  </div>
                </div>

                {/* REWARD ENGINEERING */}
                <div className="p-5 rounded-lg bg-[#080d14] border border-slate-800/80 flex flex-col justify-between space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">REWARD ENGINEERING</span>
                    </div>
                    <h3 className="text-lg font-mono font-bold text-white mb-2">Sharpe & Turnover Penalty</h3>
                    <p className="text-xs text-slate-400 leading-relaxed font-mono mb-4">
                      The reward function balances high returns with low transaction friction:
                    </p>
                    <div className="p-3 rounded bg-slate-950 border border-slate-900 text-center font-mono text-xs text-emerald-400 mb-4 select-all">
                      Reward_t = Sharpe_t - λ * ||w_t - w_t-1||
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed font-mono">
                      The transaction turnover penalty factor (<span className="text-amber-400">λ</span>) restricts high-frequency rebalancing, keeping annualized portfolio turnover low for tax and execution efficiency.
                    </p>
                  </div>
                </div>

              </div>
            </div>

            {/* Model Progression & Tech Stack Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* V1 RELEASE */}
              <div className="panel border border-slate-800 rounded-lg overflow-hidden bg-[#0d141f] lg:col-span-1">
                <div className="px-5 py-3.5 font-mono text-[10px] font-bold uppercase tracking-widest"
                  style={{ color: "#64748b", borderBottom: `1px solid ${DIM}`, background: '#090f17' }}>
                  V1 RELEASE / RESEARCH FOUNDATION
                </div>
                <div className="p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                    <h3 className="text-sm font-mono font-bold text-white">Closed-Universe SAC Model</h3>
                    <span className="text-[9px] font-mono text-slate-500 uppercase">Legacy 11 Assets</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed font-mono">
                    Our initial research foundation (V1) operated on a closed universe of 11 large-cap assets. It utilized a permutation-invariant SAC reinforcement learning network and achieved a <strong>113.31%</strong> total return (vs Nifty 50's 36.49%) in a 3-year walk-forward backtest.
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed font-mono">
                    While the risk-adjusted Sharpe ratio was a verified <strong>1.045</strong>, the model suffered from hyperactive trading with a <strong>16.47x</strong> annual turnover rate due to lack of slippage/friction penalties.
                  </p>
                  <div className="grid grid-cols-3 gap-2 pt-2 text-center">
                    <div className="p-2 rounded bg-slate-950 border border-slate-900">
                      <div className="text-[9px] font-mono text-slate-500 uppercase mb-0.5">Return</div>
                      <div className="text-xs font-bold text-emerald-400">113.31%</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-900">
                      <div className="text-[9px] font-mono text-slate-500 uppercase mb-0.5">Sharpe</div>
                      <div className="text-xs font-bold text-amber-400">1.045</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-900">
                      <div className="text-[9px] font-mono text-slate-500 uppercase mb-0.5">Turnover</div>
                      <div className="text-xs font-bold text-rose-400">16.47x</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* V2 RELEASE */}
              <div className="panel border border-slate-800 rounded-lg overflow-hidden bg-[#0d141f] lg:col-span-1">
                <div className="px-5 py-3.5 font-mono text-[10px] font-bold uppercase tracking-widest flex items-center justify-between"
                  style={{ color: "#64748b", borderBottom: `1px solid ${DIM}`, background: '#090f17' }}>
                  <span>V2 RELEASE / PRODUCTION READY</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                </div>
                <div className="p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                    <h3 className="text-sm font-mono font-bold text-white">Open-Universe Ticker-Agnostic</h3>
                    <span className="text-[9px] font-mono text-emerald-400 uppercase">NSE & Nifty 500</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed font-mono">
                    In V2, we refined the model into a ticker-agnostic engine supporting an open NSE universe (including custom Nifty 500 equities).
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed font-mono">
                    We integrated a Transaction Cost Penalty directly into the Gymnasium reward function, restricting turnover. Additionally, we layered in a multi-model pipeline including XGBoost directional classifiers and Groq Llama-3 AI advisory reports to synthesize macro and news context.
                  </p>
                  <div className="p-2 rounded bg-slate-950 border border-slate-900 text-center text-[10px] font-mono text-emerald-400/80">
                    ✓ Restricted Turnover & Slippage Penalties Implemented
                  </div>
                </div>
              </div>

              {/* TECHNOLOGY STACK */}
              <div className="panel border border-slate-800 rounded-lg overflow-hidden bg-[#0d141f] lg:col-span-1">
                <div className="px-5 py-3.5 font-mono text-[10px] font-bold uppercase tracking-widest"
                  style={{ color: "#64748b", borderBottom: `1px solid ${DIM}`, background: '#090f17' }}>
                  TECHNOLOGY STACK & DEPENDENCIES
                </div>
                <div className="p-5">
                  <div className="flex flex-wrap gap-2">
                    {[
                      "Next.js 14",
                      "TypeScript",
                      "Tailwind CSS",
                      "FastAPI",
                      "Python 3.10+",
                      "Stable-Baselines3",
                      "Groq / Llama-3",
                      "Lightweight Charts",
                      "Fyers API & WebSockets",
                      "Vercel"
                    ].map((tech) => (
                      <span key={tech} className="px-3 py-1.5 rounded text-xs font-mono text-slate-300 bg-slate-950 border border-slate-900 hover:border-emerald-500/30 transition-colors">
                        {tech}
                      </span>
                    ))}
                  </div>
                  <div className="mt-5 pt-3 border-t border-slate-800/60 text-[10px] font-mono text-slate-500 leading-relaxed">
                    Designed for secure, distributed deployment: local FastAPI sidecar process execution for institutional data handling, combined with static web exports.
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

      </div>

      {/* ── Chatbot Overlay ───────────────────────────────────── */}
      <div className={`fixed bottom-0 right-0 z-[100] transform transition-transform duration-500 ease-out ${isChatOpen ? "translate-y-0 translate-x-0" : "translate-y-full translate-x-4 opacity-0 pointer-events-none"}`} style={{ width: "400px", height: "600px", right: "24px", bottom: "80px" }}>
        <div className="flex flex-col h-full rounded-2xl shadow-2xl border overflow-hidden" style={{ background: "#0a1118", borderColor: `${G}44` }}>
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ background: "#0d141e", borderColor: DIM }}>
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-3 h-3 rounded-full absolute -top-1 -right-1 animate-ping" style={{ background: G }} />
                <div className="w-3 h-3 rounded-full absolute -top-1 -right-1" style={{ background: G }} />
                <span style={{ fontFamily: "'Yatra One', system-ui", color: 'white', fontSize: '20px' }}>धन</span>
              </div>
              <div>
                <h3 className="text-sm font-bold text-white tracking-wide flex items-center gap-1.5">
                  <em style={{ fontStyle: 'italic', color: G, fontFamily: "'Playfair Display', serif" }}>Niti</em> Advisor
                </h3>
                <p className="text-[10px] text-slate-400 font-mono">Mem0 Context Enabled</p>
              </div>
            </div>
            <button onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-[#1e2d40] transition-colors">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
          
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ background: "#070a0f" }}>
            {chatMessages.length === 0 && (
              <div className="text-center mt-12 space-y-3 opacity-60">
                <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center border" style={{ borderColor: DIM, background: "#111827" }}>
                  <span style={{ fontFamily: "'Yatra One', system-ui", color: G, fontSize: '24px' }}>धन</span>
                </div>
                <p className="text-xs text-slate-400 font-mono max-w-[250px] mx-auto">Ask me about your portfolio, market regimes, or algorithmic trading principles.</p>
              </div>
            )}
            {chatMessages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed shadow-sm ${msg.role === "user" ? "text-slate-100" : "text-slate-300"}`}
                  style={{
                    background: msg.role === "user" ? "#1e2d40" : "#111827",
                    border: `1px solid ${msg.role === "user" ? "#334155" : `${G}33`}`,
                    borderBottomRightRadius: msg.role === "user" ? "4px" : "12px",
                    borderBottomLeftRadius: msg.role === "user" ? "12px" : "4px",
                  }}>
                  {msg.content ? renderMessageContent(msg.content) : (msg.role === "assistant" && <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: G }} />)}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
          
          {/* Input */}
          <div className="p-4 border-t" style={{ background: "#0d141e", borderColor: DIM }}>
            <div className="flex gap-2">
              <input 
                type="text" 
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !chatLoading && handleSendChatMessage()}
                placeholder="Ask DhanNiti AI..." 
                className="flex-1 bg-[#070a0f] border rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#00d97e] transition-colors"
                style={{ borderColor: DIM }}
                disabled={chatLoading}
              />
              <button 
                onClick={handleSendChatMessage}
                disabled={chatLoading || !chatInput.trim()}
                className="w-10 h-10 flex items-center justify-center rounded-lg bg-[#00d97e] text-black hover:bg-[#00c270] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Floating Chat Toggle Button */}
      <button 
        onClick={() => setIsChatOpen(!isChatOpen)}
        className="fixed bottom-6 right-6 z-[90] w-14 h-14 rounded-full flex items-center justify-center shadow-[0_0_20px_rgba(0,217,126,0.3)] transition-transform hover:scale-110 active:scale-95"
        style={{ background: "linear-gradient(135deg, #0f2618, #00d97e)", border: `2px solid #00d97e` }}
      >
        {isChatOpen ? (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
        )}
      </button>

    </div>
  </div>
  );
}
