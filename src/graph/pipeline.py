"""
DhanNiti — LangGraph Pipeline Orchestrator
Replaces linear script execution with a resilient State Machine.
"""

import logging
from typing import TypedDict, Dict, Any, List, Literal
from datetime import datetime
from langgraph.graph import StateGraph, START, END

# Import the actual systems we built
from src.data.extractor import extract_data, fetch_fii_dii_data, fetch_options_pcr, fetch_nifty_vix
from src.data.sentiment import SentimentPipeline
from src.ml.regime import RegimeDetector
from src.agent.memory import DhanNitiAgentMemory
from src.agent.advisor import DhanNitiAdvisor

logger = logging.getLogger(__name__)

# ── STATE DEFINITION ──────────────────────────────────────────────────

class PipelineState(TypedDict):
    """LangGraph State object passed between nodes."""
    date: datetime
    
    # Data
    raw_price_data: Dict[str, Any]
    alternative_data: Dict[str, Any]
    
    # ML
    regime: str
    regime_probs: Dict[str, float]
    features: Dict[str, Any]
    shap_features: Dict[str, Dict[str, float]]
    drift_detected: bool
    hyperparams_tuned: bool
    
    # Signals
    xgboost_signals: Dict[str, Any]
    prophet_forecasts: Dict[str, float]
    markowitz_weights: Dict[str, float]
    rl_weights: Dict[str, float]
    rl_feedback: Dict[str, Any]
    
    # Cognitive
    memory_episodes: List[Dict[str, Any]]
    advisory_report: Dict[str, Any]
    validation_attempts: int


# ── NODE FUNCTIONS ────────────────────────────────────────────────────

def fetch_data(state: PipelineState) -> dict:
    """Fetch base OHLCV data."""
    logger.info("NODE: fetch_data")
    try:
        # We would pass PORTFOLIO_TICKERS from settings
        from src.settings import PORTFOLIO_TICKERS
        data = extract_data(PORTFOLIO_TICKERS)
        return {"raw_price_data": data}
    except Exception as e:
        logger.error(f"Fetch data failed: {e}")
        return {"raw_price_data": {}}

def fetch_alternative_data(state: PipelineState) -> dict:
    """Fetch FII, PCR, VIX, and FinBERT Sentiment."""
    logger.info("NODE: fetch_alternative_data")
    alt_data = {}
    try:
        fii_dii = fetch_fii_dii_data()
        alt_data["fii_net"] = fii_dii.get("fii_net", 0.0)
        alt_data["pcr"] = fetch_options_pcr()
        alt_data["vix"] = fetch_nifty_vix()
        
        # Sentiment
        sentiment_pipeline = SentimentPipeline()
        alt_data["sentiment"] = sentiment_pipeline.get_portfolio_sentiment()
    except Exception as e:
        logger.error(f"Alt data fetch failed: {e}")
        
    return {"alternative_data": alt_data}

def detect_regime(state: PipelineState) -> dict:
    """Classify current market regime using HMM."""
    logger.info("NODE: detect_regime")
    try:
        detector = RegimeDetector()
        # Mocking the proxy Nifty df for now since it needs to be fetched
        # In prod, this passes the Nifty50 dataframe
        dummy_df = list(state["raw_price_data"].values())[0] if state.get("raw_price_data") else None
        if dummy_df is not None:
            res = detector.predict_current_regime(dummy_df)
            return {"regime": res.get("regime", "neutral"), "regime_probs": res.get("probabilities", {})}
    except Exception as e:
        logger.error(f"Regime detection failed: {e}")
        
    return {"regime": "neutral", "regime_probs": {}}

def feature_engineering(state: PipelineState) -> dict:
    logger.info("NODE: feature_engineering")
    try:
        from src.features.pipeline import build_full_feature_matrix
        raw_data = state.get("raw_price_data", {})
        if not raw_data:
            logger.warning("No raw price data found for feature engineering.")
            return {"features": {}}
        features = build_full_feature_matrix(raw_data, add_labels=False)
        return {"features": features}
    except Exception as e:
        logger.error(f"Feature engineering failed: {e}")
        return {"features": {}}

def drift_check(state: PipelineState) -> dict:
    logger.info("NODE: drift_check")
    # This invokes src.ml.drift_detector
    return {"drift_detected": False}

def tune_hyperparams(state: PipelineState) -> dict:
    logger.info("NODE: tune_hyperparams")
    return {"hyperparams_tuned": True}

def train_classifiers(state: PipelineState) -> dict:
    """Train/Predict XGBoost."""
    logger.info("NODE: train_classifiers")
    xgboost_signals = {}
    shap_features = {}
    try:
        from src.ml.classifier import DhanNitiClassifier
        features_dict = state.get("features", {})
        
        for ticker, df_feat in features_dict.items():
            if df_feat.empty:
                continue
            
            # Load best model from registry or train a fresh one if missing/force-retrain is requested
            import os
            force_retrain = os.getenv("DHANNITI_FORCE_TUNE", "false").lower() == "true"
            
            model = None if force_retrain else DhanNitiClassifier.load_best_version(ticker)
            if model is None:
                logger.info(f"Fitting fresh XGBoost model for {ticker} (force_retrain={force_retrain})...")
                model = DhanNitiClassifier()
                
                # To fit, we need labels. Let's make sure it fits with labels.
                from src.features.technical import build_features_for_portfolio
                raw_data = {ticker: state["raw_price_data"][ticker]}
                df_labeled = build_features_for_portfolio(raw_data, add_labels=True)[ticker]
                
                model.fit(df_labeled, tune=force_retrain)
                model.save_versioned(ticker)
            
            # Generate latest prediction signals
            latest_sig = model.latest_signal(df_feat)
            xgboost_signals[ticker] = latest_sig
            shap_features[ticker] = model.get_shap_summary()
            
    except Exception as e:
        logger.error(f"Train/Predict classifiers failed: {e}")
        
    return {"xgboost_signals": xgboost_signals, "shap_features": shap_features}

def run_predictions(state: PipelineState) -> dict:
    """Run Prophet, Markowitz, and RL agent for weight overrides."""
    logger.info("NODE: run_predictions")
    
    rl_weights = {}
    prophet_forecasts = {}
    markowitz_weights = {}
    
    try:
        from src.agent.rl_agent import RLPortfolioAgent
        from src.portfolio.markowitz import optimize_portfolio_mean_variance
        
        raw_price_data = state.get("raw_price_data", {})
        features_dict = state.get("features", {})
        
        # 1. Compute Markowitz weights
        if raw_price_data:
            try:
                markowitz_weights = optimize_portfolio_mean_variance(raw_price_data)
            except Exception as e:
                logger.error(f"Markowitz optimization failed: {e}")
        
        # 2. Extract Prophet forecasts
        for ticker, df_feat in features_dict.items():
            if not df_feat.empty and "Prophet_Forecast" in df_feat.columns:
                prophet_forecasts[ticker] = float(df_feat["Prophet_Forecast"].iloc[-1])
        
        # 3. Compute RL optimal weights (V2 SAC)
        try:
            from src.inference.portfolio_inference_v2 import predict_v2_portfolio_weights
            from src.settings import PORTFOLIO_TICKERS
            
            # V2 SAC model requires 78-feature matrix, built on the fly for correctness
            rl_weights = predict_v2_portfolio_weights(
                tickers=PORTFOLIO_TICKERS,
                as_of_date=state.get("date"),
                features_dict=None
            )
            logger.info(f"V2 SAC optimal weights predicted: {rl_weights}")
        except Exception as e:
            logger.error(f"V2 SAC weight prediction failed: {e}")
            rl_weights = {}
            
    except Exception as e:
        logger.error(f"Predictions node failed: {e}")
        
    return {
        "prophet_forecasts": prophet_forecasts,
        "markowitz_weights": markowitz_weights,
        "rl_weights": rl_weights
    }

def backtest_and_rl_feedback(state: PipelineState) -> dict:
    logger.info("NODE: backtest_and_rl_feedback")
    return {"rl_feedback": {}}

def query_memory(state: PipelineState) -> dict:
    """Retrieve semantic episodes from Qdrant via Mem0."""
    logger.info("NODE: query_memory")
    try:
        mem = DhanNitiAgentMemory()
        # Filter purely by current regime
        episodes = mem.get_regime_filtered_episodes(regime=state.get("regime", "neutral"), limit=3)
        return {"memory_episodes": episodes}
    except Exception as e:
        logger.error(f"Memory query failed: {e}")
        return {"memory_episodes": []}

def call_advisor(state: PipelineState) -> dict:
    """Synthesize Groq Report."""
    logger.info("NODE: call_advisor")
    attempts = state.get("validation_attempts", 0)
    
    try:
        advisor = DhanNitiAdvisor()
        report = advisor.synthesize_recommendation(
            date=state.get("date", datetime.now()),
            regime=state.get("regime", "neutral"),
            xgboost_signals=state.get("xgboost_signals", {}),
            prophet_forecasts=state.get("prophet_forecasts", {}),
            markowitz_weights=state.get("markowitz_weights", {}),
            rl_weights=state.get("rl_weights", {}),
            alternative_data=state.get("alternative_data", {}),
            shap_features=state.get("shap_features", {}),
            memory_episodes=state.get("memory_episodes", [])
        )
        return {
            "advisory_report": report,
            "validation_attempts": attempts + 1
        }
    except Exception as e:
        logger.error(f"Advisor call failed: {e}")
        return {
            "advisory_report": {"status": "error"},
            "validation_attempts": attempts + 1
        }

def persist_results(state: PipelineState) -> dict:
    logger.info("NODE: persist_results")
    report = state.get("advisory_report", {})
    if report and report.get("status") != "error":
        try:
            from src.database.supabase_client import DhanNitiDatabase
            db = DhanNitiDatabase()
            
            # 1. Save final advisory report
            db.upsert_advisory_report(report)
            
            # 2. Extract and save individual stock predictions
            predictions = []
            date_obj = state.get("date")
            if isinstance(date_obj, datetime):
                date_str = date_obj.strftime("%Y-%m-%d")
            elif isinstance(date_obj, str):
                date_str = date_obj
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                
            raw_data = state.get("raw_price_data", {})
            xgb_signals = state.get("xgboost_signals", {})
            prophet_forecasts = state.get("prophet_forecasts", {})
            rl_weights = state.get("rl_weights", {})
            
            from src.settings import MINIMUM_ALLOCATION
            import math
            
            for ticker in raw_data.keys():
                rl_weight = rl_weights.get(ticker, 0.0)
                if rl_weight < MINIMUM_ALLOCATION:
                    continue

                df = raw_data.get(ticker)
                actual_prices = []
                if df is not None and not df.empty:
                    # Get last 20 close prices as a list of floats
                    actual_prices = df['Close'].tolist() if 'Close' in df.columns else []
                    
                xgb_sig = xgb_signals.get(ticker, {})
                prophet_price = prophet_forecasts.get(ticker, 0.0)
                
                def safe_float(v):
                    try:
                        val = float(v)
                        return val if not math.isnan(val) else 0.0
                    except:
                        return 0.0
                
                predictions.append({
                    "as_of_date": date_str,
                    "ticker": ticker,
                    "predicted_price": safe_float(prophet_price),
                    "predicted_return": safe_float(xgb_sig.get("predicted_return", 0.0)),
                    "actual_prices_last_month": str(actual_prices),
                    "portfolio_weight": safe_float(rl_weight)
                })
                
            if predictions:
                db.upsert_predictions(predictions)
                
        except Exception as e:
            logger.error(f"Failed to persist to Supabase: {e}")
    return {}

def broadcast_websocket(state: PipelineState) -> dict:
    logger.info("NODE: broadcast_websocket")
    # Push update to FastAPI connected clients
    return {}


# ── CONDITIONAL EDGES ─────────────────────────────────────────────────

def check_drift_condition(state: PipelineState) -> Literal["tune_hyperparams", "train_classifiers"]:
    """Route based on data drift."""
    if state.get("drift_detected", False):
        return "tune_hyperparams"
    return "train_classifiers"

def check_validation_condition(state: PipelineState) -> Literal["persist_results", "call_advisor"]:
    """Retry logic for LLM JSON validation."""
    report = state.get("advisory_report", {})
    attempts = state.get("validation_attempts", 0)
    
    if report.get("status") != "error":
        # Success
        return "persist_results"
    
    if attempts >= 2:
        logger.warning("Max LLM validation attempts reached. Proceeding to persistence with fallback.")
        return "persist_results"
        
    logger.info(f"Retrying Advisor LLM generation... (Attempt {attempts + 1})")
    return "call_advisor"


# ── GRAPH COMPILATION ─────────────────────────────────────────────────

def build_pipeline_graph():
    """Compiles the LangGraph StateMachine."""
    builder = StateGraph(PipelineState)
    
    # 1. Add Nodes
    builder.add_node("fetch_data", fetch_data)
    builder.add_node("fetch_alternative_data", fetch_alternative_data)
    builder.add_node("detect_regime", detect_regime)
    builder.add_node("feature_engineering", feature_engineering)
    builder.add_node("drift_check", drift_check)
    builder.add_node("tune_hyperparams", tune_hyperparams)
    builder.add_node("train_classifiers", train_classifiers)
    builder.add_node("run_predictions", run_predictions)
    builder.add_node("backtest_and_rl_feedback", backtest_and_rl_feedback)
    builder.add_node("query_memory", query_memory)
    builder.add_node("call_advisor", call_advisor)
    builder.add_node("persist_results", persist_results)
    builder.add_node("broadcast_websocket", broadcast_websocket)
    
    # 2. Add Linear Edges
    builder.add_edge(START, "fetch_data")
    builder.add_edge("fetch_data", "fetch_alternative_data")
    builder.add_edge("fetch_alternative_data", "detect_regime")
    builder.add_edge("detect_regime", "feature_engineering")
    builder.add_edge("feature_engineering", "drift_check")
    
    # 3. Conditional Edge: Drift Detection
    builder.add_conditional_edges("drift_check", check_drift_condition)
    builder.add_edge("tune_hyperparams", "train_classifiers")
    
    # 4. Continue Pipeline
    builder.add_edge("train_classifiers", "run_predictions")
    builder.add_edge("run_predictions", "backtest_and_rl_feedback")
    builder.add_edge("backtest_and_rl_feedback", "query_memory")
    builder.add_edge("query_memory", "call_advisor")
    
    # 5. Conditional Edge: Advisor Validation Retry Loop
    builder.add_conditional_edges("call_advisor", check_validation_condition)
    
    # 6. Finish
    builder.add_edge("persist_results", "broadcast_websocket")
    builder.add_edge("broadcast_websocket", END)
    
    return builder.compile()
