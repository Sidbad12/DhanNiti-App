"""
Persist portfolio recommend results to Supabase and run scheduled daily inference.

GET /portfolio/recommend: fresh PPO + XGBoost + HMM + Qdrant + Groq synthesis → persist.
GET /portfolio/current: last persisted snapshot from Supabase only (no inference).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.agent.advisor import DhanNitiAdvisor
from src.agent.memory import DhanNitiAgentMemory
from src.database.supabase_client import DhanNitiDatabase
from src.data.extractor import (
    extract_data,
    fetch_fii_dii_data,
    fetch_nifty_vix,
    fetch_options_pcr,
)
from src.features.pipeline import build_full_feature_matrix
from src.inference.portfolio_inference import (
    MODEL_VERSION_V1,
    predict_portfolio_weights,
)
from src.ml.regime import RegimeDetector
from src.portfolio.markowitz import optimize_portfolio_mean_variance
from src.settings import BACKTEST_CONFIG, PORTFOLIO_TICKERS, START_DATE

logger = logging.getLogger(__name__)

SOURCE_V1_RECOMMEND = "v1_ppo_recommend"
SOURCE_GROQ_RECOMMEND = "v1_ppo_groq"


def _xgb_predicted_return(signal: dict[str, Any]) -> float:
    """Directional return proxy from classifier probabilities."""
    bull = float(signal.get("prob_bullish", 0.33))
    bear = float(signal.get("prob_bearish", 0.33))
    return bull - bear


def compute_expected_return(
    weights: dict[str, float],
    xgboost_signals: dict[str, dict[str, Any]],
) -> float:
    """Dot product: portfolio weights × XGBoost predicted returns per ticker."""
    total = 0.0
    for ticker, weight in weights.items():
        sig = xgboost_signals.get(ticker, {})
        total += float(weight) * _xgb_predicted_return(sig)
    return round(total, 6)


def _memory_episodes_to_citations(episodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for ep in episodes:
        date = str(ep.get("date", "unknown"))
        summary = (ep.get("market_summary") or ep.get("summary") or "")[:200]
        reward = ep.get("reward", 0.0)
        citations.append(
            {
                "date": date,
                "similarity": summary or f"Regime {ep.get('regime', 'unknown')} episode",
                "outcome": f"reward={float(reward):.3f}",
            }
        )
    return citations


def _merge_memory_citations(
    groq_citations: list[Any],
    episodes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Prefer Groq citations; backfill from Qdrant episodes when the LLM returns none."""
    merged: list[dict[str, str]] = []
    seen_dates: set[str] = set()

    for item in groq_citations or []:
        if isinstance(item, dict):
            row = {
                "date": str(item.get("date", "")),
                "similarity": str(item.get("similarity", "")),
                "outcome": str(item.get("outcome", "")),
            }
        else:
            row = {
                "date": str(getattr(item, "date", "")),
                "similarity": str(getattr(item, "similarity", "")),
                "outcome": str(getattr(item, "outcome", "")),
            }
        if row["date"]:
            seen_dates.add(row["date"])
            merged.append(row)

    for row in _memory_episodes_to_citations(episodes):
        if row["date"] not in seen_dates:
            merged.append(row)
            seen_dates.add(row["date"])

    return merged[:5]


def _detect_regime(raw_data: dict[str, Any], as_of: str) -> tuple[str, dict[str, float]]:
    benchmark = BACKTEST_CONFIG.get("benchmark", "^NSEI")
    try:
        nifty_frames = extract_data([benchmark], START_DATE, as_of)
        nifty_df = nifty_frames.get(benchmark)
        if nifty_df is None or nifty_df.empty:
            for df in raw_data.values():
                if df is not None and not df.empty:
                    nifty_df = df
                    break
        if nifty_df is None or nifty_df.empty:
            return "unknown", {}

        detector = RegimeDetector()
        result = detector.predict_current_regime(nifty_df)
        return result.get("regime", "unknown"), result.get("probabilities", {})
    except Exception:
        logger.exception("HMM regime detection failed")
        return "unknown", {}


def _gather_xgboost_signals(
    features_dict: dict[str, Any],
    raw_data: dict[str, Any],
    force_retrain: bool = False,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]]]:
    from src.features.technical import build_features_for_portfolio
    from src.ml.classifier import DhanNitiClassifier

    xgboost_signals: dict[str, dict[str, Any]] = {}
    shap_features: dict[str, dict[str, float]] = {}

    for ticker in features_dict.keys():
        df_feat = features_dict.get(ticker)
        if df_feat is None or df_feat.empty:
            continue
        try:
            model = None if force_retrain else DhanNitiClassifier.load_best_version(ticker)
            if model is None:
                raw_t = raw_data.get(ticker)
                if raw_t is None or raw_t.empty:
                    continue
                model = DhanNitiClassifier()
                df_labeled = build_features_for_portfolio({ticker: raw_t}, add_labels=True)[ticker]
                import os
                tune = os.getenv("DHANNITI_FORCE_TUNE", "false").lower() == "true"
                model.fit(df_labeled, tune=tune)
                model.save_versioned(ticker)

            sig = model.latest_signal(df_feat)
            sig["predicted_return"] = _xgb_predicted_return(sig)
            xgboost_signals[ticker] = sig
            shap_features[ticker] = model.get_shap_summary()
        except Exception:
            logger.exception("XGBoost signal failed for %s", ticker)

    return xgboost_signals, shap_features


def _prophet_forecasts(features_dict: dict[str, Any]) -> dict[str, float]:
    forecasts: dict[str, float] = {}
    for ticker, df_feat in features_dict.items():
        if df_feat is not None and not df_feat.empty and "Prophet_Forecast" in df_feat.columns:
            forecasts[ticker] = float(df_feat["Prophet_Forecast"].iloc[-1])
    return forecasts


def _fetch_alternative_data() -> dict[str, Any]:
    alt: dict[str, Any] = {}
    try:
        fii = fetch_fii_dii_data()
        alt["fii_net"] = fii.get("fii_net", 0.0)
        alt["pcr"] = fetch_options_pcr()
        alt["vix"] = fetch_nifty_vix()
    except Exception:
        logger.exception("Alternative data fetch failed")
    return alt


def _log_recommend_episode(
    report: dict[str, Any],
    *,
    regime: str,
    xgboost_signals: dict[str, dict[str, Any]],
) -> None:
    """Persist today's run to Qdrant episodic memory for future citations."""
    try:
        mem = DhanNitiAgentMemory()
        as_of = report.get("as_of") or report.get("date") or datetime.now().strftime("%Y-%m-%d")
        summary = (report.get("reasoning") or report.get("market_overview") or "")[:500]
        ml_preds = {
            ticker: float(sig.get("predicted_return", _xgb_predicted_return(sig)))
            for ticker, sig in xgboost_signals.items()
        }
        mem.log_episode(
            date=datetime.strptime(as_of, "%Y-%m-%d"),
            market_summary=summary or f"Portfolio recommend {as_of} regime={regime}",
            ml_predictions=ml_preds,
            weights_allocated=report.get("allocations", {}),
            reward=float(report.get("expected_return", 0.0)),
            regime=regime,
        )
    except Exception:
        logger.exception("Failed to log recommend episode to memory")


def _query_memory_episodes(regime: str, alternative_data: dict[str, Any]) -> list[dict[str, Any]]:
    mem = DhanNitiAgentMemory()
    query_text = (
        f"NSE India portfolio. Regime: {regime}. "
        f"VIX: {alternative_data.get('vix', 'unknown')}. "
        f"FII net: {alternative_data.get('fii_net', 'unknown')}."
    )
    similar = mem.query_similar_episodes(query_text, limit=3)
    by_regime = mem.get_regime_filtered_episodes(regime=regime, limit=3)

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for ep in similar + by_regime:
        key = str(ep.get("date", id(ep)))
        if key in seen:
            continue
        seen.add(key)
        merged.append(ep)
    return merged[:5]


def build_quant_report(
    allocations: dict[str, float],
    *,
    as_of: str,
    model_version: str = MODEL_VERSION_V1,
    tickers: list[str] | None = None,
    regime: str = "unknown",
    expected_return: float = 0.0,
    regime_probs: dict[str, float] | None = None,
) -> dict[str, Any]:
    """PPO-only payload (quant path; no Groq narrative)."""
    ticker_list = list(tickers or PORTFOLIO_TICKERS)
    total = sum(allocations.values())
    report: dict[str, Any] = {
        "date": as_of,
        "as_of": as_of,
        "allocations": allocations,
        "ppo_allocations": allocations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
        "weight_sum": round(total, 6),
        "tickers": ticker_list,
        "source": SOURCE_V1_RECOMMEND,
        "regime": regime,
        "reasoning": (
            "V1 PPO portfolio weights from portfolio_inference "
            "(quant path; Groq not used)."
        ),
        "risk_flags": [],
        "llm_confidence": 0.0,
        "expected_return": expected_return,
        "memory_citations": [],
    }
    if regime_probs:
        report["regime_probs"] = regime_probs
    return report


# Backward-compatible alias used in tests
build_recommend_report = build_quant_report


def _predictions_rows(
    as_of: str,
    allocations: dict[str, float],
    xgboost_signals: dict[str, dict[str, Any]],
    prophet_forecasts: dict[str, float],
) -> list[dict[str, Any]]:
    from src.settings import MINIMUM_ALLOCATION
    rows: list[dict[str, Any]] = []
    for ticker, weight in allocations.items():
        if float(weight) < MINIMUM_ALLOCATION:
            continue
        sig = xgboost_signals.get(ticker, {})
        rows.append(
            {
                "as_of_date": as_of,
                "ticker": ticker,
                "predicted_price": float(prophet_forecasts.get(ticker, 0.0)),
                "predicted_return": float(sig.get("predicted_return", _xgb_predicted_return(sig))),
                "actual_prices_last_month": "[]",
                "portfolio_weight": float(weight),
            }
        )
    return rows


def persist_recommend_report(report: dict[str, Any]) -> bool:
    """Upsert advisory_reports.full_report and portfolio_predictions rows."""
    db = DhanNitiDatabase()
    as_of = report.get("as_of") or report.get("date") or datetime.now().strftime("%Y-%m-%d")
    advisory_ok = db.upsert_advisory_report({**report, "date": as_of})

    xgb = report.get("xgboost_signals") or {}
    prophet = report.get("prophet_forecasts") or {}
    predictions_ok = db.upsert_predictions(
        _predictions_rows(as_of, report.get("allocations", {}), xgb, prophet)
    )
    if advisory_ok and predictions_ok:
        logger.info(
            "Persisted recommend for %s (%d tickers, source=%s)",
            as_of,
            len(report.get("allocations", {})),
            report.get("source"),
        )
    elif advisory_ok:
        logger.warning(
            "Advisory report saved for %s but portfolio_predictions upsert failed "
            "(check Supabase RLS or use service_role in SUPABASE_KEY).",
            as_of,
        )
    elif predictions_ok:
        logger.warning("Predictions saved but advisory_reports upsert failed for %s", as_of)
    return advisory_ok


def run_portfolio_recommend(
    as_of: str | None = None,
    *,
    persist: bool = True,
    model_name: str = "ppo_dhanniti",
    use_groq: bool = True,
) -> dict[str, Any]:
    """
    Fresh recommend: PPO inference + HMM regime + XGBoost + Qdrant + Groq synthesis.
    Optionally persists to Supabase (advisory_reports + portfolio_predictions).
    """
    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m-%d")

    logger.info("Portfolio recommend starting as_of=%s", as_of)

    if not use_groq:
        raw_data = extract_data(list(PORTFOLIO_TICKERS), START_DATE, as_of)
        features_dict = build_full_feature_matrix(raw_data, add_labels=False)
        ppo_only = predict_portfolio_weights(
            tickers=PORTFOLIO_TICKERS,
            as_of_date=as_of,
            model_name=model_name,
            features_dict=features_dict,
        )
        regime, regime_probs = _detect_regime(raw_data, as_of)
        xgboost_signals, _ = _gather_xgboost_signals(features_dict, raw_data)
        expected_return = compute_expected_return(ppo_only, xgboost_signals)
        report = build_quant_report(
            ppo_only,
            as_of=as_of,
            tickers=list(PORTFOLIO_TICKERS),
            regime=regime,
            expected_return=expected_return,
            regime_probs=regime_probs,
        )
        _log_recommend_episode(report, regime=regime, xgboost_signals=xgboost_signals)
        if persist:
            persist_recommend_report(report)
        return report

    raw_data = extract_data(list(PORTFOLIO_TICKERS), START_DATE, as_of)
    features_dict = build_full_feature_matrix(raw_data, add_labels=False)

    ppo_allocations = predict_portfolio_weights(
        tickers=PORTFOLIO_TICKERS,
        as_of_date=as_of,
        model_name=model_name,
        features_dict=features_dict,
    )

    regime, regime_probs = _detect_regime(raw_data, as_of)
    xgboost_signals, shap_features = _gather_xgboost_signals(features_dict, raw_data)
    prophet_forecasts = _prophet_forecasts(features_dict)
    alternative_data = _fetch_alternative_data()

    markowitz_weights: dict[str, float] = {}
    try:
        if raw_data:
            markowitz_weights = optimize_portfolio_mean_variance(raw_data)
    except Exception:
        logger.exception("Markowitz optimization failed")

    memory_episodes = _query_memory_episodes(regime, alternative_data)
    expected_return = compute_expected_return(ppo_allocations, xgboost_signals)

    advisor = DhanNitiAdvisor()
    synthesis = advisor.synthesize_recommendation(
        date=datetime.strptime(as_of, "%Y-%m-%d"),
        regime=regime,
        xgboost_signals=xgboost_signals,
        prophet_forecasts=prophet_forecasts,
        markowitz_weights=markowitz_weights,
        rl_weights=ppo_allocations,
        alternative_data=alternative_data,
        shap_features=shap_features,
        memory_episodes=memory_episodes,
    )

    memory_citations = _merge_memory_citations(
        synthesis.get("memory_citations", []),
        memory_episodes,
    )

    total = sum(ppo_allocations.values())
    report: dict[str, Any] = {
        "date": as_of,
        "as_of": as_of,
        "allocations": ppo_allocations,
        "ppo_allocations": ppo_allocations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION_V1,
        "weight_sum": round(total, 6),
        "tickers": list(PORTFOLIO_TICKERS),
        "source": SOURCE_GROQ_RECOMMEND,
        "regime": regime,
        "regime_probs": regime_probs,
        "regime_commentary": synthesis.get("regime_commentary", ""),
        "reasoning": synthesis.get("reasoning", ""),
        "risk_flags": synthesis.get("risk_flags", []),
        "llm_confidence": float(synthesis.get("llm_confidence", 0.0)),
        "expected_return": expected_return,
        "memory_citations": memory_citations,
        "stock_breakdowns": synthesis.get("stock_breakdowns", {}),
        "market_overview": synthesis.get("market_overview", ""),
        "memory_note": synthesis.get("memory_note", ""),
        "xgboost_signals": {t: {k: v for k, v in s.items() if k != "shap"} for t, s in xgboost_signals.items()},
        "prophet_forecasts": prophet_forecasts,
    }

    _log_recommend_episode(report, regime=regime, xgboost_signals=xgboost_signals)

    if persist:
        persist_recommend_report(report)

    logger.info(
        "Portfolio recommend done regime=%s llm_confidence=%.2f expected_return=%.4f citations=%d",
        report["regime"],
        report["llm_confidence"],
        report["expected_return"],
        len(report["memory_citations"]),
    )
    return report


SOURCE_V2_RECOMMEND = "v2_sac_recommend"
MODEL_VERSION_V2 = "v2"


def run_portfolio_recommend_v2(
    as_of: str | None = None,
    *,
    persist: bool = True,
    model_path: str = "models/v2/v2_sac_final.zip",
    tickers: list[str] | None = None,
    use_groq: bool = True,
    start_date: str | None = None,
    force_retrain: bool = True,
) -> dict[str, Any]:
    """
    V2 SAC-powered recommendation.

    Scores each ticker independently via the ticker-agnostic SAC agent, then
    normalises into a portfolio allocation.  The rest of the quant stack
    (HMM regime, XGBoost signals, Prophet, Qdrant memory, optional Groq
    narrative) is identical to the V1 path so the response schema is compatible.
    """
    from src.inference.portfolio_inference_v2 import predict_v2_portfolio_weights, V2_PORTFOLIO_UNIVERSE

    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m-%d")

    active_tickers = list(tickers or V2_PORTFOLIO_UNIVERSE)
    logger.info("V2 SAC portfolio recommend starting as_of=%s tickers=%d", as_of, len(active_tickers))

    # ── 1. Feature data ───────────────────────────────────────────────────
    from src.settings import START_DATE
    start_dt = start_date or START_DATE
    raw_data = extract_data(active_tickers, start_dt, as_of)
    features_dict = build_full_feature_matrix(raw_data, add_labels=False)

    # ── 2. SAC inference ──────────────────────────────────────────────────
    sac_allocations = predict_v2_portfolio_weights(
        tickers=active_tickers,
        as_of_date=as_of,
        model_path=model_path,
        features_dict=None,   # let the V2 module fetch V2 features internally
        start_date=start_dt,
    )

    # ── 3. Supporting quant signals ───────────────────────────────────────
    regime, regime_probs = _detect_regime(raw_data, as_of)
    xgboost_signals, shap_features = _gather_xgboost_signals(features_dict, raw_data, force_retrain=force_retrain)
    prophet_forecasts = _prophet_forecasts(features_dict)
    alternative_data = _fetch_alternative_data()
    expected_return = compute_expected_return(sac_allocations, xgboost_signals)

    # ── 4. Optional Groq narrative ────────────────────────────────────────
    memory_citations: list[dict[str, str]] = []
    synthesis: dict[str, Any] = {}
    if use_groq:
        try:
            memory_episodes = _query_memory_episodes(regime, alternative_data)
            advisor = DhanNitiAdvisor()
            synthesis = advisor.synthesize_recommendation(
                date=datetime.strptime(as_of, "%Y-%m-%d"),
                regime=regime,
                xgboost_signals=xgboost_signals,
                prophet_forecasts=prophet_forecasts,
                markowitz_weights={},
                rl_weights=sac_allocations,
                alternative_data=alternative_data,
                shap_features=shap_features,
                memory_episodes=memory_episodes,
            )
            memory_citations = _merge_memory_citations(
                synthesis.get("memory_citations", []), memory_episodes
            )
        except Exception:
            logger.exception("Groq synthesis failed in V2 recommend — continuing quant-only.")

    total = sum(sac_allocations.values())
    report: dict[str, Any] = {
        "date": as_of,
        "as_of": as_of,
        "allocations": sac_allocations,
        "sac_allocations": sac_allocations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION_V2,
        "model_path": model_path,
        "weight_sum": round(total, 6),
        "tickers": active_tickers,
        "start_date": start_dt,
        "source": SOURCE_V2_RECOMMEND,
        "regime": regime,
        "regime_probs": regime_probs,
        "regime_commentary": synthesis.get("regime_commentary", ""),
        "reasoning": synthesis.get("reasoning", "V2 SAC ticker-agnostic allocation."),
        "risk_flags": synthesis.get("risk_flags", []),
        "llm_confidence": float(synthesis.get("llm_confidence", 0.0)),
        "expected_return": expected_return,
        "memory_citations": memory_citations,
        "stock_breakdowns": synthesis.get("stock_breakdowns", {}),
        "market_overview": synthesis.get("market_overview", ""),
        "xgboost_signals": {
            t: {k: v for k, v in s.items() if k != "shap"}
            for t, s in xgboost_signals.items()
        },
        "prophet_forecasts": prophet_forecasts,
    }

    _log_recommend_episode(report, regime=regime, xgboost_signals=xgboost_signals)

    if persist:
        persist_recommend_report(report)

    logger.info(
        "V2 SAC recommend done regime=%s expected_return=%.4f active_positions=%d",
        regime,
        expected_return,
        sum(1 for w in sac_allocations.values() if w > 0),
    )
    return report


def run_daily_portfolio_recommend() -> None:
    """APScheduler entrypoint — full Groq recommend for today using V2 SAC."""
    logger.info("Scheduled daily portfolio recommend starting")
    try:
        run_portfolio_recommend_v2(persist=True)
        logger.info("Scheduled daily V2 portfolio recommend finished")
    except Exception:
        logger.exception("Scheduled daily portfolio recommend failed")
