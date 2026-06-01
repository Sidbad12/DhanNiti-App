"""
DhanNiti — Cognitive Advisor
Synthesizes XGBoost signals + Prophet forecasts + RL weights +
Markowitz weights + Qdrant episodic memory + Regime + Alt Data + SHAP
into a Groq-powered natural-language recommendation with structured JSON output.

# fm-key: src/agent/advisor.py
# fm-value: Cognitive advisor that aggregates ML predictions, technical indicator signals, and episodic memory into structured Groq suggestions.
# fm-scope: file
# fm-links: src/settings.py, src/agent/tools.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from src.agent.groq_client import GroqAdvisorClient
from src.settings import (
    MINIMUM_ALLOCATION,
    MAXIMUM_ALLOCATION,
    PORTFOLIO_TICKERS,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────────

def _build_prompt(
    date_str: str,
    regime: str,
    xgboost_signals: dict[str, dict],
    prophet_forecasts: dict[str, float],
    markowitz_weights: dict[str, float],
    rl_weights: dict[str, float],
    alternative_data: dict[str, Any],
    shap_features: dict[str, dict[str, float]],
    memory_episodes: list[dict[str, Any]],
) -> str:
    """Build the structured user prompt for Groq."""
    lines: list[str] = [
        f"DATE: {date_str}",
        f"MARKET: NSE India (Nifty-50 universe)",
        f"DETECTED REGIME: {regime}",
        f"CONSTRAINTS: min_weight={MINIMUM_ALLOCATION}, max_weight={MAXIMUM_ALLOCATION}",
        "",
        "=== Alternative Data ===",
        f"FII Net Institutional Flow: {alternative_data.get('fii_net', 'Unknown')}",
        f"Nifty Put-Call Ratio (PCR): {alternative_data.get('pcr', 'Unknown')}",
        f"India VIX: {alternative_data.get('vix', 'Unknown')}",
    ]

    # Add sentiment if available
    sentiment = alternative_data.get("sentiment", {})
    if sentiment:
        lines.append("News Sentiment (FinBERT):")
        for t, score in sentiment.items():
            lines.append(f"  {t}: {score}")

    lines += ["", "=== XGBoost Signals & Top SHAP Features ==="]
    for ticker, sig in xgboost_signals.items():
        action     = sig.get("action", "HOLD")
        confidence = sig.get("confidence", 0.0)
        
        # Format SHAP
        stock_shap = shap_features.get(ticker, {})
        shap_str = " | ".join(f"{f}: {v:+.2f}" for f, v in list(stock_shap.items())[:3])
        if not shap_str:
            shap_str = "None available"
            
        lines.append(
            f"  {ticker}: action={action} conf={confidence:.2f} -> SHAP Drivers: {shap_str}"
        )

    lines += ["", "=== Prophet Price Forecasts ==="]
    for ticker, price in prophet_forecasts.items():
        lines.append(f"  {ticker}: ₹{price:.2f}")

    lines += ["", "=== Weight Suggestions ==="]
    for ticker in rl_weights.keys():
        mw = markowitz_weights.get(ticker, 0.0)
        rw = rl_weights.get(ticker, 0.0)
        lines.append(f"  {ticker}: Markowitz={mw:.4f} | RL_Agent={rw:.4f}")

    lines += ["", "=== Episodic Memory (Similar Past States) ==="]
    if memory_episodes:
        for i, ep in enumerate(memory_episodes[:3], 1):
            date    = ep.get("date", "unknown")
            ep_regime = ep.get("regime", "unknown")
            summary = ep.get("market_summary", "")[:120]
            reward  = ep.get("reward", 0.0)
            weights = ep.get("weights_allocated", {})
            top_w   = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
            top_str = ", ".join(f"{t}={w:.2f}" for t, w in top_w)
            lines.append(
                f"  [{i}] {date} (Regime: {ep_regime}): {summary} | reward={reward:.3f} | top={top_str}"
            )
    else:
        lines.append("  No similar past episodes found.")

    lines += [
        "",
        "=== Authoritative SAC Allocation (fixed — do not change) ===",
    ]
    for ticker in rl_weights.keys():
        rw = rl_weights.get(ticker, 0.0)
        lines.append(f"  {ticker}: SAC_weight={rw:.4f}")

    lines += [
        "",
        "=== Your Task ===",
        "Explain the fixed SAC allocation above using the signals and memory. "
        "Return JSON matching the schema (reasoning, risk_flags, stock_notes, "
        "memory_citations, confidence, regime_commentary). Do NOT output weights.",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# ADVISOR CLASS
# ─────────────────────────────────────────────────────────────

class DhanNitiAdvisor:
    """
    Cognitive advisor: synthesizes all ML outputs + memory into a
    Groq-powered structured recommendation using Instructor.
    """

    def __init__(self) -> None:
        self._llm = GroqAdvisorClient()

    def synthesize_recommendation(
        self,
        date: datetime,
        regime: str,
        xgboost_signals: dict[str, dict],
        prophet_forecasts: dict[str, float],
        markowitz_weights: dict[str, float],
        rl_weights: dict[str, float],
        alternative_data: dict[str, Any] | None = None,
        shap_features: dict[str, dict[str, float]] | None = None,
        memory_episodes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Narrative synthesis pipeline (L4):
        1. Build structured prompt (PPO weights are fixed in the prompt)
        2. Call Groq for reasoning / risk_flags / citations only
        3. Enrich per-stock breakdowns using PPO weights (not LLM weights)
        4. Return narrative fields — allocations are set by the caller (PPO)
        """
        memory_episodes = memory_episodes or []
        alternative_data = alternative_data or {}
        shap_features = shap_features or {}
        date_str = date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date)

        # ── 1. Build prompt ───────────────────────────────────
        logger.info(f"Building Groq prompt for regime: {regime}")
        prompt = _build_prompt(
            date_str=date_str,
            regime=regime,
            xgboost_signals=xgboost_signals,
            prophet_forecasts=prophet_forecasts,
            markowitz_weights=markowitz_weights,
            rl_weights=rl_weights,
            alternative_data=alternative_data,
            shap_features=shap_features,
            memory_episodes=memory_episodes,
        )

        # ── 2. Call Groq (Instructor handles validation) ──────
        logger.info("Calling Groq LLM with Instructor …")
        llm_response = self._llm.call(prompt)

        # ── 3. Build per-stock breakdowns (PPO weights are authoritative) ──
        stock_breakdowns: dict[str, dict] = {}
        stock_notes = llm_response.get("stock_notes", {})

        for ticker in rl_weights.keys():
            sig = xgboost_signals.get(ticker, {})
            forecast = prophet_forecasts.get(ticker, 0.0)
            mw = markowitz_weights.get(ticker, 0.0)
            rw = rl_weights.get(ticker, 0.0)

            stock_breakdowns[ticker] = {
                "action": sig.get("action", "HOLD"),
                "confidence": sig.get("confidence", 0.0),
                "prob_bullish": sig.get("prob_bullish", 0.0),
                "prob_bearish": sig.get("prob_bearish", 0.0),
                "prob_neutral": sig.get("prob_neutral", 0.0),
                "prophet_forecast": forecast,
                "markowitz_weight": mw,
                "rl_weight": rw,
                "blended_weight": 0.5 * mw + 0.5 * rw,
                "final_weight": rw,
                "llm_note": stock_notes.get(ticker, ""),
            }

        # ── 4. Assemble narrative report (no allocations — caller uses rl_weights) ──
        report = {
            "date": date_str,
            "stock_breakdowns": stock_breakdowns,
            "reasoning": llm_response.get("reasoning", ""),
            "risk_flags": llm_response.get("risk_flags", []),
            "memory_citations": llm_response.get("memory_citations", []),
            "llm_confidence": float(llm_response.get("confidence", 0.0)),
            "regime_commentary": llm_response.get(
                "regime_commentary", llm_response.get("regime", regime)
            ),
            "market_overview": (
                f"DhanNiti advisory for {date_str}. "
                f"HMM regime: {regime}. "
                f"{llm_response.get('reasoning', '')}"
            ),
            "memory_note": (
                f"{len(memory_episodes)} similar past episodes retrieved."
                if memory_episodes
                else "No similar episodes in memory."
            ),
            "generated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Narrative synthesis complete | confidence={report['llm_confidence']:.2f}"
        )
        logger.info(f"PPO weights (unchanged): {json.dumps(rl_weights, indent=2)}")

        if report["risk_flags"]:
            logger.warning(f"Risk flags: {report['risk_flags']}")

        return report