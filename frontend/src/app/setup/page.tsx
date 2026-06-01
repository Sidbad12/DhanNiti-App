"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";

export default function SetupPage() {
  const [step, setStep] = useState(1);
  const [isTauri, setIsTauri] = useState(false);

  // Form state
  const [supabaseUrl, setSupabaseUrl] = useState("");
  const [supabaseKey, setSupabaseKey] = useState("");
  const [databaseUrl, setDatabaseUrl] = useState(""); // optional for auto SQL migration
  const [groqKey, setGroqKey] = useState("");
  const [qdrantUrl, setQdrantUrl] = useState("");
  const [qdrantKey, setQdrantKey] = useState("");
  const [mem0Key, setMem0Key] = useState("");
  const [fyersClient, setFyersClient] = useState("");
  const [fyersSecret, setFyersSecret] = useState("");
  const [useFyers, setUseFyers] = useState(true);
  const [portfolioTickers, setPortfolioTickers] = useState(
    "RELIANCE.NS, TCS.NS, HDFCBANK.NS, INFY.NS, ICICIBANK.NS, HINDUNILVR.NS, ITC.NS, SBIN.NS, BHARTIARTL.NS, LT.NS, LIQUIDBEES.NS"
  );

  // Status & Logs
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logOutput, setLogOutput] = useState<string[]>([]);
  const [setupFinished, setSetupFinished] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && (window as any).__TAURI_INTERNALS__) {
      setIsTauri(true);
    }
  }, []);

  const addLog = (msg: string) => {
    setLogOutput((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (!text) return;

      const lines = text.split(/\r?\n/);
      let importedSupabaseUrl = "";
      let importedSupabaseKey = "";
      let importedGroqKey = "";
      let importedQdrantUrl = "";
      let importedQdrantKey = "";
      let importedMem0Key = "";
      let importedFyersClient = "";
      let importedFyersSecret = "";
      let importedTickers = "";

      lines.forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) return;
        const index = trimmed.indexOf("=");
        if (index === -1) return;
        const key = trimmed.slice(0, index).trim();
        const val = trimmed.slice(index + 1).trim().replace(/^["']|["']$/g, "");

        if (key === "SUPABASE_URL") importedSupabaseUrl = val;
        else if (key === "SUPABASE_KEY" || key === "SUPABASE_ANON_KEY") {
          if (val) importedSupabaseKey = val;
        }
        else if (key === "GROQ_API_KEY") importedGroqKey = val;
        else if (key === "QDRANT_URL") importedQdrantUrl = val;
        else if (key === "QDRANT_API_KEY") importedQdrantKey = val;
        else if (key === "MEM0_API_KEY") importedMem0Key = val;
        else if (key === "FYERS_CLIENT_ID") importedFyersClient = val;
        else if (key === "FYERS_SECRET_KEY") importedFyersSecret = val;
        else if (key === "PORTFOLIO_TICKERS") importedTickers = val;
      });

      if (importedSupabaseUrl) setSupabaseUrl(importedSupabaseUrl);
      if (importedSupabaseKey) setSupabaseKey(importedSupabaseKey);
      if (importedGroqKey) setGroqKey(importedGroqKey);
      if (importedQdrantUrl) setQdrantUrl(importedQdrantUrl);
      if (importedQdrantKey) setQdrantKey(importedQdrantKey);
      if (importedMem0Key) setMem0Key(importedMem0Key);
      if (importedFyersClient) {
        setFyersClient(importedFyersClient);
        setUseFyers(true);
      }
      if (importedFyersSecret) setFyersSecret(importedFyersSecret);
      if (importedTickers) setPortfolioTickers(importedTickers);

      addLog("✓ Successfully parsed and imported credentials from local file.");
      setStep(2);
    };
    reader.readAsText(file);
  };

  const handleSaveAndMigrate = async () => {
    setLoading(true);
    setError(null);
    setLogOutput([]);
    setStep(6);

    try {
      addLog("Initializing environment saving pipeline...");

      if (typeof window === "undefined" || !(window as any).__TAURI_INTERNALS__) {
        throw new Error("This setup configuration wizard is only supported inside the Tauri desktop app shell.");
      }

      const { invoke } = await import("@tauri-apps/api/core");

      // 1. Save Environment variables
      addLog("Saving keys and custom stock universe to .env...");
      await invoke("save_env_file", {
        supabaseUrl,
        supabaseKey,
        groqKey,
        qdrantUrl,
        qdrantKey,
        mem0Key,
        fyersClient: useFyers ? fyersClient : "",
        fyersSecret: useFyers ? fyersSecret : "",
        portfolioTickers: portfolioTickers.split(",").map(s => s.trim()).filter(Boolean).join(","),
      });
      addLog("✓ Environment configuration files successfully written.");

      // 2. SQL database schema migration
      if (databaseUrl.trim()) {
        addLog("Applying SQL tables and indices to your Supabase instance. Please wait...");
        try {
          const res = await invoke("run_supabase_init", { databaseUrl });
          addLog("✓ SQL Migration Output:");
          addLog(String(res));
          addLog("✓ Supabase tables successfully initialized.");
        } catch (e: any) {
          addLog(`⚠ Supabase auto-migration warning/failure: ${e}`);
          addLog("Don't worry, you can apply sql/consolidated_schema.sql manually in your Supabase dashboard later.");
        }
      } else {
        addLog("No PostgreSQL connection string provided. Skipping direct database schema application.");
        addLog("Please make sure to run sql/consolidated_schema.sql manually in your Supabase SQL Editor.");
      }

      addLog("✓ Setup sequence finished. Spawning sidecar servers...");
      await invoke("restart_sidecars");
      setSetupFinished(true);
    } catch (e: any) {
      addLog(`✗ Error: ${e.message || e}`);
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const colors = {
    bg: "#070a0f",
    panel: "#0b131f",
    border: "rgba(0, 217, 126, 0.15)",
    textG: "#00d97e",
    gold: "#c9a84c",
  };

  return (
    <div className="min-h-screen flex items-center justify-center py-12 px-6 font-sans text-slate-300" style={{ background: colors.bg }}>
      <div className="max-w-3xl w-full p-8 rounded-2xl border transition-all duration-500 shadow-2xl space-y-6"
           style={{ borderColor: colors.border, background: `linear-gradient(180deg, ${colors.panel} 0%, ${colors.bg} 100%)` }}>
        
        {/* Title */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-mono text-[10px] font-bold tracking-widest"
               style={{ background: "rgba(0, 217, 126, 0.08)", color: colors.textG, border: "1px solid rgba(0, 217, 126, 0.2)" }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: colors.textG }} />
            DISTRIBUTED PACKAGE INSTALLER
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight sm:text-4xl">
            DhanNiti <span style={{ color: colors.gold }}>Setup Wizard</span>
          </h1>
          <p className="text-slate-400 text-sm max-w-md mx-auto">
            Configure your local environment and connect cloud services (Supabase, Groq, Qdrant) in minutes.
          </p>
        </div>

        {/* Wizard Steps */}
        <div className="flex items-center justify-center gap-2 font-mono text-xs text-slate-500 border-b pb-4 border-slate-800">
          <span className={step === 1 ? "text-white font-bold" : ""}>1. Mode</span>
          <span>→</span>
          <span className={step === 2 ? "text-white font-bold" : ""}>2. Database</span>
          <span>→</span>
          <span className={step === 3 ? "text-white font-bold" : ""}>3. APIs</span>
          <span>→</span>
          <span className={step === 4 ? "text-white font-bold" : ""}>4. Tickers</span>
          <span>→</span>
          {useFyers && (
            <>
              <span className={step === 5 ? "text-white font-bold" : ""}>5. Live Data</span>
              <span>→</span>
            </>
          )}
          <span className={step === 6 ? "text-white font-bold" : ""}>{useFyers ? "6" : "5"}. Setup</span>
        </div>

        {/* Step 1: Mode Select */}
        {step === 1 && (
          <div className="space-y-6">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">Choose Execution Mode</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => { setUseFyers(false); setStep(2); }}
                className="p-5 rounded-xl border text-left hover:border-emerald-500/50 hover:bg-slate-900/30 transition-all space-y-2 border-slate-850"
              >
                <div className="text-emerald-400 font-mono font-bold text-sm">LIMITED MODE (EOD Backtests)</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  No broker credentials required. Uses Yahoo Finance EOD data. Perfect for testing, backtesting, and offline analysis.
                </p>
              </button>

              <button
                type="button"
                onClick={() => { setUseFyers(true); setStep(2); }}
                className="p-5 rounded-xl border text-left hover:border-amber-500/50 hover:bg-slate-900/30 transition-all space-y-2 border-slate-850"
              >
                <div className="text-amber-400 font-mono font-bold text-sm">LIVE TRADING MODE (Fyers)</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Connects to Fyers broker WebSocket for live orderbook, 50-level depth of market, real-time volume profile, and live portfolio rebalancing.
                </p>
              </button>
            </div>

            <div className="relative flex py-2 items-center">
              <div className="flex-grow border-t border-slate-800"></div>
              <span className="flex-shrink mx-4 text-xs font-mono text-slate-500">OR</span>
              <div className="flex-grow border-t border-slate-800"></div>
            </div>

            <div className="flex justify-center">
              <label className="flex items-center gap-2 px-6 py-3 border border-slate-700 hover:border-emerald-500/50 hover:bg-slate-900/30 rounded-xl text-xs font-mono cursor-pointer transition-all text-slate-300">
                <span className="text-emerald-400 font-bold text-sm">↑</span> Import Existing .env File
                <input type="file" accept=".env" onChange={handleFileImport} className="hidden" />
              </label>
            </div>

            <div className="text-center text-xs text-slate-500 font-mono">
              Note: All modes write configuration parameters locally. No credentials are sent to our servers.
            </div>
          </div>
        )}

        {/* Step 2: Database Settings */}
        {step === 2 && (
          <div className="space-y-4">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">Supabase Configurations</h3>
            
            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Supabase URL *</label>
              <input
                type="text"
                value={supabaseUrl}
                onChange={(e) => setSupabaseUrl(e.target.value)}
                placeholder="https://your-project-id.supabase.co"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Supabase Service Key / Anon Key *</label>
              <input
                type="password"
                value={supabaseKey}
                onChange={(e) => setSupabaseKey(e.target.value)}
                placeholder="eyJhbGciOiJIUzI1NiIsIn..."
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">
                PostgreSQL connection URI (Optional)
              </label>
              <input
                type="text"
                value={databaseUrl}
                onChange={(e) => setDatabaseUrl(e.target.value)}
                placeholder="postgresql://postgres:password@db.supabase.co:5432/postgres"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
              <span className="text-[10px] text-slate-500 block">
                Providing the Postgres link allows the setup wizard to automatically initialize the SQL tables.
              </span>
            </div>

            <div className="flex justify-between pt-4">
              <button type="button" onClick={() => setStep(1)} className="px-4 py-2 border border-slate-700 hover:border-slate-500 text-xs font-mono rounded-lg transition-all">
                Back
              </button>
              <button
                type="button"
                disabled={!supabaseUrl || !supabaseKey}
                onClick={() => setStep(3)}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-black font-mono text-xs font-bold rounded-lg transition-all"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 3: API & Memory Settings */}
        {step === 3 && (
          <div className="space-y-4">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">AI & Episodic Memory Keys</h3>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Groq API Key *</label>
              <input
                type="password"
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
                placeholder="gsk_xxxxxxxxxxxx"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
              <span className="text-[10px] text-slate-500 block">Required for the natural language portfolio advisors.</span>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Qdrant Cluster URL *</label>
              <input
                type="text"
                value={qdrantUrl}
                onChange={(e) => setQdrantUrl(e.target.value)}
                placeholder="https://your-cluster-id.cloud.qdrant.io"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Qdrant API Key *</label>
              <input
                type="password"
                value={qdrantKey}
                onChange={(e) => setQdrantKey(e.target.value)}
                placeholder="xxxxx-xxxxx-xxxxx"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
              <span className="text-[10px] text-slate-500 block">Required. Cloud Qdrant cluster stores RL agent memory buffers.</span>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Mem0 API Key (Optional)</label>
              <input
                type="password"
                value={mem0Key}
                onChange={(e) => setMem0Key(e.target.value)}
                placeholder="mem0_xxxxxxxxxxxx"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="flex justify-between pt-4">
              <button type="button" onClick={() => setStep(2)} className="px-4 py-2 border border-slate-700 hover:border-slate-500 text-xs font-mono rounded-lg transition-all">
                Back
              </button>
              <button
                type="button"
                disabled={!groqKey || !qdrantUrl || !qdrantKey}
                onClick={() => setStep(4)}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-black font-mono text-xs font-bold rounded-lg transition-all"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Portfolio Tickers */}
        {step === 4 && (
          <div className="space-y-4">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">Configure Stock Universe</h3>
            
            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Stock Tickers (NSE / Yahoo Finance format, comma-separated) *</label>
              <textarea
                value={portfolioTickers}
                onChange={(e) => setPortfolioTickers(e.target.value)}
                placeholder="RELIANCE.NS, TCS.NS, HDFCBANK.NS..."
                rows={4}
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all resize-none"
              />
              <span className="text-[10px] text-slate-500 block">
                Define the asset universe that the reinforcement learning agent will optimize. Specify NSE stocks suffixing '.NS' (e.g. INFIBEAM.NS).
              </span>
            </div>

            <div className="flex justify-between pt-4">
              <button type="button" onClick={() => setStep(3)} className="px-4 py-2 border border-slate-700 hover:border-slate-500 text-xs font-mono rounded-lg transition-all">
                Back
              </button>
              <button
                type="button"
                disabled={!portfolioTickers.trim()}
                onClick={() => {
                  if (useFyers) {
                    setStep(5);
                  } else {
                    handleSaveAndMigrate();
                  }
                }}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-black font-mono text-xs font-bold rounded-lg transition-all"
              >
                {useFyers ? "Next" : "Complete Setup"}
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Fyers Credentials */}
        {step === 5 && (
          <div className="space-y-4">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">Fyers API Integration</h3>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Fyers App Client ID *</label>
              <input
                type="text"
                value={fyersClient}
                onChange={(e) => setFyersClient(e.target.value)}
                placeholder="XS12345678"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-mono uppercase tracking-widest text-slate-400">Fyers Secret Key *</label>
              <input
                type="password"
                value={fyersSecret}
                onChange={(e) => setFyersSecret(e.target.value)}
                placeholder="XYZ123456789"
                className="w-full font-mono text-xs px-3.5 py-2.5 rounded-lg border border-slate-800 bg-[#0d1117] text-white focus:border-emerald-500 outline-none transition-all"
              />
            </div>

            <div className="flex justify-between pt-4">
              <button type="button" onClick={() => setStep(4)} className="px-4 py-2 border border-slate-700 hover:border-slate-500 text-xs font-mono rounded-lg transition-all">
                Back
              </button>
              <button
                type="button"
                disabled={!fyersClient || !fyersSecret}
                onClick={handleSaveAndMigrate}
                className="px-6 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-black font-mono text-xs font-bold rounded-lg transition-all"
              >
                Complete Setup
              </button>
            </div>
          </div>
        )}

        {/* Step 6: Execution Logs / Progress */}
        {step === 6 && (
          <div className="space-y-4">
            <h3 className="text-lg font-mono font-bold text-white uppercase tracking-wider">Automating Setup Tasks</h3>
            
            <div className="font-mono text-[11px] p-4 rounded-lg border bg-black text-slate-300 max-h-[300px] overflow-y-auto space-y-1.5"
                 style={{ borderColor: "rgba(255, 255, 255, 0.08)" }}>
              {logOutput.map((log, idx) => (
                <div key={idx} className={log.includes("✓") ? "text-emerald-400" : log.includes("✗") ? "text-red-500" : ""}>
                  {log}
                </div>
              ))}
              {loading && <div className="text-slate-500 animate-pulse">Running execution commands...</div>}
            </div>

            {error && (
              <div className="p-4 rounded-lg bg-red-950/20 border border-red-900/50 text-red-400 text-xs font-mono">
                Error running configuration: {error}
              </div>
            )}

            {setupFinished && (
              <div className="space-y-4">
                <div className="p-4 rounded-lg bg-emerald-950/20 border border-emerald-900/50 text-emerald-400 text-xs font-mono">
                  ✓ Environment successfully configured. You can now access the full dashboard view.
                </div>
                
                <div className="flex justify-center pt-2">
                  <Link href="/dashboard" className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-black font-mono text-xs font-bold uppercase tracking-wider rounded-lg transition-all">
                    Go to Dashboard
                  </Link>
                </div>
              </div>
            )}

            {error && (
              <div className="flex gap-2 justify-end pt-4">
                <button
                  type="button"
                  onClick={() => setStep(useFyers ? 5 : 4)}
                  className="px-4 py-2 border border-slate-700 hover:border-slate-500 text-xs font-mono rounded-lg transition-all"
                >
                  Edit Keys
                </button>
                <button
                  type="button"
                  onClick={handleSaveAndMigrate}
                  className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-black font-mono text-xs font-bold rounded-lg transition-all"
                >
                  Retry Setup
                </button>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
