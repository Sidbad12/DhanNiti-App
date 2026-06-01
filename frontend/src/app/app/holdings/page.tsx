"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  fetchHoldings,
  fetchHoldingsGap,
  addHolding,
  deleteHolding,
  simulateRebalanceCost,
} from "@/lib/api";
import type { Holding, HoldingsSummary, GapItem } from "@/types/api";

const G = "#00d97e";
const R = "#ff4d6a";
const DIM = "#1e2d40";

export default function HoldingsPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [summary, setSummary] = useState<HoldingsSummary | null>(null);
  const [gapAnalysis, setGapAnalysis] = useState<GapItem[]>([]);
  const [portfolioValue, setPortfolioValue] = useState(0);
  const [simCost, setSimCost] = useState<number | null>(null);
  const [simLoading, setSimLoading] = useState(false);

  // Form State
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyDate, setBuyDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [holdingsData, gapData] = await Promise.all([
        fetchHoldings(),
        fetchHoldingsGap(),
      ]);

      setHoldings(holdingsData.holdings);
      setSummary(holdingsData.summary);
      setGapAnalysis(gapData.gap_analysis);
      setPortfolioValue(gapData.portfolio_value);

      // Auto-simulate rebalance cost if there are holdings
      if (holdingsData.holdings.length > 0 && gapData.gap_analysis.length > 0) {
        const currentWeights: Record<string, number> = {};
        const targetWeights: Record<string, number> = {};
        gapData.gap_analysis.forEach((item) => {
          currentWeights[item.ticker] = item.held_weight;
          targetWeights[item.ticker] = item.ppo_weight;
        });

        setSimLoading(true);
        try {
          const simRes = await simulateRebalanceCost(
            currentWeights,
            targetWeights,
            holdingsData.summary.total_current_value
          );
          setSimCost(simRes.estimated_cost_inr);
        } catch {
          // ignore non-critical simulation error
        } finally {
          setSimLoading(false);
        }
      } else {
        setSimCost(null);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddHolding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker || !quantity || !buyPrice || !buyDate) return;

    setActionLoading(true);
    try {
      let formattedTicker = ticker.trim().toUpperCase();
      if (!formattedTicker.endsWith(".NS") && formattedTicker !== "LIQUIDBEES" && formattedTicker !== "LIQUIDBEES.NS") {
        formattedTicker = `${formattedTicker}.NS`;
      }
      if (formattedTicker === "LIQUIDBEES") {
        formattedTicker = "LIQUIDBEES.NS";
      }

      await addHolding({
        ticker: formattedTicker,
        quantity: parseFloat(quantity),
        buy_price: parseFloat(buyPrice),
        buy_date: buyDate,
        notes: notes.trim() || undefined,
      });

      // Reset form
      setTicker("");
      setQuantity("");
      setBuyPrice("");
      setNotes("");

      // Reload
      await loadData();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to add holding");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteHolding = async (id: string) => {
    if (!confirm("Are you sure you want to delete this holding?")) return;

    setActionLoading(true);
    try {
      await deleteHolding(id);
      await loadData();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to delete holding");
    } finally {
      setActionLoading(false);
    }
  };

  const fmt = {
    pct: (v: number) => `${v.toFixed(2)}%`,
    inr: (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`,
    inrRaw: (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`,
    date: (d: string) => new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }),
    tick: (t: string) => t.replace(".NS", ""),
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6" style={{ background: "#070a0f" }}>
        <div className="panel max-w-md w-full p-6 text-center space-y-4 border border-red-500/20">
          <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mx-auto text-red-500 text-sm font-mono font-bold">
            ERROR
          </div>
          <h2 className="text-white font-bold text-lg font-mono">Local Server Offline</h2>
          <p className="text-sm text-slate-400 font-mono leading-relaxed">
            Personal Portfolio tracking, live P&L computation, and Gap Analysis require the DhanNiti local server to be running.
          </p>
          <div className="bg-[#111827] p-3 rounded text-left text-xs text-slate-500 font-mono border border-slate-800 break-words">
            Failed to connect to: {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}
          </div>
          <div className="text-xs text-slate-500 font-mono">
            Start the server locally using:
            <code className="block bg-[#111827] text-yellow-400 p-2 rounded mt-1 select-all">
              poetry run uvicorn src.api.server:app --host 127.0.0.1 --port 8000
            </code>
          </div>
          <div className="flex gap-3 pt-2">
            <Link href="/app/dashboard" className="flex-1 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded font-mono text-xs transition-colors">
              Dashboard
            </Link>
            <button onClick={loadData} className="flex-1 px-4 py-2 bg-[#00d97e] hover:opacity-90 text-black font-bold rounded font-mono text-xs transition-all">
              Recheck
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "#070a0f" }}>
      {/* Header */}
      <header
        className="sticky top-0 z-50 px-6 py-3 flex items-center justify-between"
        style={{ background: "#0d1117", borderBottom: `1px solid ${DIM}` }}
      >
        <div className="flex items-center gap-3">
          <Link href="/app/dashboard" className="text-slate-400 hover:text-white font-mono text-xs transition-colors">
            ← BACK TO QUANT
          </Link>
          <span className="text-slate-600">|</span>
          <span className="text-white font-bold text-lg tracking-tight">
            Personal <span style={{ color: G }}>Portfolio</span>
          </span>
        </div>

        <button
          onClick={loadData}
          disabled={loading || actionLoading}
          className="px-3 py-1 text-xs font-mono font-bold rounded transition-colors"
          style={{ background: "#111827", color: "#64748b", border: `1px solid ${DIM}` }}
        >
          {loading ? "LOADING..." : "↻ REFRESH"}
        </button>
      </header>

      {loading && holdings.length === 0 ? (
        <div className="flex h-[80vh] items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: `${G} transparent transparent transparent` }} />
            <span className="font-mono text-sm text-slate-500">Loading Portfolio Layer...</span>
          </div>
        </div>
      ) : (
        <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
          {/* 1. Summary Bar */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="panel p-4 flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest text-[#64748b] font-mono">Total Invested</span>
                <span className="text-2xl font-bold font-mono text-white">{fmt.inr(summary.total_invested)}</span>
              </div>
              <div className="panel p-4 flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest text-[#64748b] font-mono">Current Value</span>
                <span className="text-2xl font-bold font-mono text-white">{fmt.inr(summary.total_current_value)}</span>
              </div>
              <div className="panel p-4 flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest text-[#64748b] font-mono">Unrealised P&L</span>
                <span className="text-2xl font-bold font-mono" style={{ color: summary.total_unrealised_pnl >= 0 ? G : R }}>
                  {summary.total_unrealised_pnl >= 0 ? "+" : ""}{fmt.inr(summary.total_unrealised_pnl)}
                </span>
              </div>
              <div className="panel p-4 flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest text-[#64748b] font-mono">Absolute Return</span>
                <span className="text-2xl font-bold font-mono" style={{ color: summary.total_unrealised_pnl_pct >= 0 ? G : R }}>
                  {summary.total_unrealised_pnl_pct >= 0 ? "▲" : "▼"} {fmt.pct(summary.total_unrealised_pnl_pct)}
                </span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 2. Holdings Table */}
            <div className="lg:col-span-2 space-y-6">
              <div className="panel border border-slate-800 rounded-lg overflow-hidden">
                <div className="px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-widest border-b border-slate-800" style={{ color: "#64748b" }}>
                  Active Holdings Ledger
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-900 font-mono text-[10px] text-slate-500 uppercase">
                        <th className="p-4">Ticker</th>
                        <th className="p-4 text-right">Qty</th>
                        <th className="p-4 text-right">Avg Buy</th>
                        <th className="p-4 text-right">LTP</th>
                        <th className="p-4 text-right">Invested</th>
                        <th className="p-4 text-right">Current Value</th>
                        <th className="p-4 text-right">P&L (%)</th>
                        <th className="p-4 text-center">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holdings.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="p-8 text-center font-mono text-xs text-slate-500">
                            No holdings in ledger. Add one below to track.
                          </td>
                        </tr>
                      ) : (
                        holdings.map((h) => {
                          const pnl = h.unrealised_pnl ?? 0;
                          const pnlPct = h.unrealised_pnl_pct ?? 0;
                          return (
                            <tr key={h.id} className="border-b border-slate-900 hover:bg-[#0d111788] transition-colors font-mono text-xs text-slate-300">
                              <td className="p-4 font-bold text-white">
                                {fmt.tick(h.ticker)}
                                {h.notes && (
                                  <span className="block text-[10px] text-slate-500 font-normal mt-0.5 max-w-[120px] truncate" title={h.notes}>
                                    {h.notes}
                                  </span>
                                )}
                              </td>
                              <td className="p-4 text-right">{h.quantity}</td>
                              <td className="p-4 text-right">{fmt.inrRaw(h.buy_price)}</td>
                              <td className="p-4 text-right text-slate-400">
                                {h.current_price !== null ? fmt.inrRaw(h.current_price) : "—"}
                              </td>
                              <td className="p-4 text-right">{fmt.inr(h.invested_value)}</td>
                              <td className="p-4 text-right font-bold">
                                {h.current_value !== null ? fmt.inr(h.current_value) : "—"}
                              </td>
                              <td className="p-4 text-right font-bold" style={{ color: pnl >= 0 ? G : R }}>
                                {pnl >= 0 ? "+" : ""}{fmt.inr(pnl)}
                                <span className="block text-[10px] font-normal mt-0.5">
                                  ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
                                </span>
                              </td>
                              <td className="p-4 text-center">
                                <button
                                  onClick={() => handleDeleteHolding(h.id)}
                                  disabled={actionLoading}
                                  className="px-2 py-1 text-[10px] font-bold bg-red-950/30 hover:bg-red-500 hover:text-black border border-red-500/20 rounded transition-all text-red-500"
                                >
                                  DELETE
                                </button>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 3. Add Holding Form */}
              <div className="panel p-5 border border-slate-800 rounded-lg space-y-4">
                <div className="font-mono text-[11px] font-bold uppercase tracking-widest" style={{ color: "#64748b" }}>
                  Record New Transaction
                </div>
                <form onSubmit={handleAddHolding} className="grid grid-cols-1 md:grid-cols-5 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono text-slate-500 uppercase">Ticker</label>
                    <input
                      type="text"
                      placeholder="e.g. INFy"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value)}
                      className="px-3 py-1.5 rounded font-mono text-xs outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono text-slate-500 uppercase">Quantity</label>
                    <input
                      type="number"
                      placeholder="Shares"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      className="px-3 py-1.5 rounded font-mono text-xs outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                      step="any"
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono text-slate-500 uppercase">Buy Price (₹)</label>
                    <input
                      type="number"
                      placeholder="Price"
                      value={buyPrice}
                      onChange={(e) => setBuyPrice(e.target.value)}
                      className="px-3 py-1.5 rounded font-mono text-xs outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                      step="any"
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono text-slate-500 uppercase">Buy Date</label>
                    <input
                      type="date"
                      value={buyDate}
                      onChange={(e) => setBuyDate(e.target.value)}
                      onClick={(e) => e.currentTarget.showPicker()}
                      className="px-3 py-1.5 rounded font-mono text-xs outline-none cursor-pointer"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono text-slate-500 uppercase">Notes (Optional)</label>
                    <input
                      type="text"
                      placeholder="e.g. IPO"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      className="px-3 py-1.5 rounded font-mono text-xs outline-none"
                      style={{ background: "#111827", color: "white", border: `1px solid ${DIM}` }}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="md:col-span-5 w-full py-2 bg-[#00d97e] hover:opacity-90 disabled:opacity-50 text-black font-bold font-mono text-xs rounded transition-all mt-2"
                  >
                    {actionLoading ? "SUBMITTING..." : "ADD TRANSACTION TO LEDGER"}
                  </button>
                </form>
              </div>
            </div>

            {/* Right sidebar - 4. Gap Analysis */}
            <div className="space-y-6">
              <div className="panel border border-slate-800 rounded-lg overflow-hidden">
                <div className="px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-widest border-b border-slate-800" style={{ color: "#64748b" }}>
                  Quant Gap Analysis
                </div>

                <div className="p-4 space-y-4">
                  <p className="text-xs text-slate-400 font-mono leading-relaxed">
                    This panel compares your held holdings weights (by current market value) against DhanNiti's latest V2 SAC model allocations.
                  </p>

                  <div className="space-y-3">
                    {gapAnalysis.length === 0 ? (
                      <div className="text-center font-mono text-xs text-slate-500 py-6">
                        No gap analysis. Add holdings to compute gaps.
                      </div>
                    ) : (
                      gapAnalysis.map((item) => {
                        const gapPct = item.gap * 100;
                        const actionColor = item.action === "buy" ? G : item.action === "sell" ? R : "#64748b";
                        return (
                          <div key={item.ticker} className="bg-[#111827] p-3 rounded-lg border border-slate-800/80 font-mono text-xs space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-white">{fmt.tick(item.ticker)}</span>
                              <span
                                className="px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
                                style={{
                                  color: actionColor,
                                  background: `${actionColor}11`,
                                  border: `1px solid ${actionColor}33`,
                                }}
                              >
                                {item.action.toUpperCase()}
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-1 text-[10px] text-slate-400">
                              <div>Held: {fmt.pct(item.held_weight * 100)}</div>
                              <div>Target: {fmt.pct(item.ppo_weight * 100)}</div>
                              <div className="text-right" style={{ color: gapPct >= 0 ? G : R }}>
                                Gap: {gapPct >= 0 ? "+" : ""}{gapPct.toFixed(1)}%
                              </div>
                            </div>
                            {item.delta_inr !== 0 && (
                              <div className="text-[10px] flex justify-between pt-1 border-t border-slate-900">
                                <span className="text-slate-500">Required Trade:</span>
                                <span className="font-bold" style={{ color: item.delta_inr >= 0 ? G : R }}>
                                  {item.delta_inr >= 0 ? "BUY" : "SELL"} {fmt.inr(Math.abs(item.delta_inr))}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              {/* 5. Rebalance cost simulator */}
              {simCost !== null && (
                <div className="panel p-5 border border-slate-800 rounded-lg space-y-3">
                  <div className="font-mono text-[11px] font-bold uppercase tracking-widest text-[#64748b]">
                    Transition Cost Estimate
                  </div>
                  <p className="text-[11px] text-slate-400 font-mono leading-relaxed">
                    Estimated brokerage + STT + transaction costs on NSE to transition your ledger to V2 SAC recommended weights.
                  </p>
                  <div className="flex items-center justify-between p-3 rounded" style={{ background: "#111827", border: `1px solid ${DIM}` }}>
                    <span className="font-mono text-xs text-[#64748b]">Est. Rebalance Cost</span>
                    <span className="font-mono text-lg font-bold" style={{ color: simLoading ? "#64748b" : R }}>
                      {simLoading ? "Calculating..." : fmt.inr(simCost)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
