"""
DhanNiti — Configuration
All secrets via environment variables. Never hardcode.

# fm-key: src/settings.py
# fm-value: Global configuration module holding baseline hyperparameter grids, watchlists, portfolio parameters, and Agent Search Optimization (Factman & rgx) limits.
# fm-scope: file
# fm-links: src/agent/tools.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

import pandas as pd


# ════════════════════════════════════════════════════════════
# PORTFOLIO
# ════════════════════════════════════════════════════════════

_env_tickers = os.getenv("PORTFOLIO_TICKERS")
if _env_tickers:
    PORTFOLIO_TICKERS = [t.strip() for t in _env_tickers.split(",") if t.strip()]
else:
    PORTFOLIO_TICKERS = [
        "RELIANCE.NS",
        "TCS.NS",
        "HDFCBANK.NS",
        "INFY.NS",
        "ICICIBANK.NS",
        "HINDUNILVR.NS",
        "ITC.NS",
        "SBIN.NS",
        "BHARTIARTL.NS",
        "LT.NS",
        "LIQUIDBEES.NS",
    ]

START_DATE = "2022-01-03"
END_DATE   = datetime.now().strftime("%Y-%m-%d")

MARKET_TIMEZONE  = "Asia/Kolkata"
CURRENCY_SYMBOL  = "₹"
CURRENCY_CODE    = "INR"
MARKET_OPEN      = "09:15"
MARKET_CLOSE     = "15:30"


# ════════════════════════════════════════════════════════════
# MARKOWITZ BASELINE
# ════════════════════════════════════════════════════════════

RISK_AVERSION       = 1.0
MINIMUM_ALLOCATION  = 0.02
MAXIMUM_ALLOCATION  = 0.35
ALLOW_SHORT         = False


# ════════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ════════════════════════════════════════════════════════════

FEATURE_CONFIG = {
    # RSI periods
    "rsi_periods": [5, 10, 14, 21],

    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # Bollinger Bands
    "bbands_period": 20,
    "bbands_std": 2,

    # ATR
    "atr_period": 14,

    # Moving averages
    "sma_periods": [5, 10, 20, 50],
    "ema_periods": [5, 10, 20, 50],

    # Stochastic RSI
    "stochrsi_period": 14,

    # CCI
    "cci_period": 20,

    # Williams %R
    "willr_period": 14,

    # ROC / Momentum
    "roc_period": 10,
    "mom_period": 10,

    # Volume
    "vwma_period": 20,

    # Keltner Channel
    "kc_period": 20,

    # KST
    "kst_enabled": True,
}

PROPHET_FEATURE_CONFIG = {
    "daily_seasonality"      : False,
    "weekly_seasonality"     : True,
    "yearly_seasonality"     : True,
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10,
    "extract_components"     : ["trend", "weekly", "yearly"],
}


# ════════════════════════════════════════════════════════════
# XGBOOST CLASSIFIER
# ════════════════════════════════════════════════════════════

XGBOOST_PARAMS = {
    "n_estimators"    : 300,
    "max_depth"       : 6,
    "learning_rate"   : 0.05,
    "subsample"       : 0.9,
    "colsample_bytree": 0.8,
    "objective"       : "multi:softprob",
    "num_class"       : 3,
    "eval_metric"     : "mlogloss",
    "n_jobs"          : -1,
    "seed"            : 42,
}

XGBOOST_TUNING_GRID = {
    "n_estimators"    : [200, 400, 600],
    "max_depth"       : [4, 6, 8],
    "learning_rate"   : [0.01, 0.05, 0.1],
    "subsample"       : [0.8, 1.0],
    "colsample_bytree": [0.6, 0.8, 1.0],
}

LABEL_LOOKAHEADS  = [2, 4, 6, 8, 10]
LABEL_THRESHOLDS  = [0.01, 0.02]

SIGNAL_CONFIDENCE_THRESHOLD = 0.60

TIMESERIES_N_SPLITS = 5

ACCURACY_DRIFT_THRESHOLD = 0.50


# ════════════════════════════════════════════════════════════
# BACKTESTER
# ════════════════════════════════════════════════════════════

BACKTEST_CONFIG = {
    "stt_rate"       : 0.001,
    "brokerage_rate" : 0.0003,
    "impact_cost"    : 0.0005,
    "initial_capital": 500_000,
    "benchmark"      : "^NSEI",
}


# ════════════════════════════════════════════════════════════
# RL AGENT
# ════════════════════════════════════════════════════════════

RL_CONFIG = {
    "lookback_window"  : 30,
    "n_stocks"         : len(PORTFOLIO_TICKERS),
    "initial_capital"  : 500_000,

    "reward_metric"    : "sharpe",
    "reward_lookback"  : 20,

    "policy"           : "MlpPolicy",
    "learning_rate"    : 3e-4,
    "n_steps"          : 2048,
    "batch_size"       : 64,
    "n_epochs"         : 10,
    "gamma"            : 0.99,
    "total_timesteps"  : 500_000,

    "checkpoint_freq"  : 10_000,
    "model_save_path"  : "models/ppo_dhanniti",
}


# ════════════════════════════════════════════════════════════
# MEMORY
# ════════════════════════════════════════════════════════════

MEMORY_CONFIG = {
    "qdrant_collection"   : "dhanniti_episodes",
    "qdrant_vector_size"  : 384,
    "qdrant_distance"     : "Cosine",

    "top_k_episodes"      : 5,
    "min_episode_score"   : 0.70,

    "outcome_horizons"    : [5, 10],
}


# ════════════════════════════════════════════════════════════
# LLM
# ════════════════════════════════════════════════════════════

GROQ_MODEL       = "llama-3.1-8b-instant"
GROQ_MAX_TOKENS  = 1024
GROQ_TEMPERATURE = 0.2

ADVISOR_OUTPUT_FORMAT = "json"


# ════════════════════════════════════════════════════════════
# MLOPS
# ════════════════════════════════════════════════════════════

MLFLOW_CONFIG = {
    "experiment_name" : "dhanniti-xgboost",
    "run_tags"        : {
        "project" : "dhanniti",
        "market"  : "NSE",
        "model"   : "xgboost-classifier",
    },
    "log_shap"        : True,
    "log_confusion"   : True,
    "log_feature_imp" : True,
}

DAGSHUB_REPO_OWNER = os.getenv("DAGSHUB_USERNAME", os.getenv("DAGSHUB_REPO_OWNER", "Sidbad12"))
DAGSHUB_REPO_NAME  = os.getenv("DAGSHUB_REPO", os.getenv("DAGSHUB_REPO_NAME", "DhanNiti"))


# ════════════════════════════════════════════════════════════
# SECRETS
# ════════════════════════════════════════════════════════════

GROQ_API_KEY     = os.getenv("GROQ_API_KEY",     "")
QDRANT_URL       = os.getenv("QDRANT_URL",        "")
QDRANT_API_KEY   = os.getenv("QDRANT_API_KEY",   "")
MEM0_API_KEY     = os.getenv("MEM0_API_KEY",     "")
DAGSHUB_TOKEN    = os.getenv("DAGSHUB_TOKEN",    "")
SUPABASE_URL     = os.getenv("SUPABASE_URL",     "")
SUPABASE_KEY     = (
    os.getenv("SUPABASE_KEY", "")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)

PORTFOLIO_SCHEDULER_ENABLED = os.getenv("PORTFOLIO_SCHEDULER_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
PORTFOLIO_SCHEDULER_HOUR = int(os.getenv("PORTFOLIO_SCHEDULER_HOUR", "9"))
PORTFOLIO_SCHEDULER_MINUTE = int(os.getenv("PORTFOLIO_SCHEDULER_MINUTE", "15"))

SUPABASE_TABLE_NAME = "portfolio_predictions"
RESULTS_TABLE       = SUPABASE_TABLE_NAME


# ════════════════════════════════════════════════════════════
# NSE HOLIDAYS
# ════════════════════════════════════════════════════════════

INDIAN_MARKET_HOLIDAYS = pd.DataFrame({
    "holiday": "indian_market_holiday",
    "ds": pd.to_datetime([
        "2025-01-26", "2025-03-08", "2025-03-25", "2025-03-29",
        "2025-04-11", "2025-04-17", "2025-04-21", "2025-05-01",
        "2025-05-23", "2025-06-17", "2025-07-17", "2025-08-15",
        "2025-08-26", "2025-10-02", "2025-10-12", "2025-11-01",
        "2025-11-02", "2025-11-15", "2025-12-25",
        "2026-01-26", "2026-03-14", "2026-03-31", "2026-04-10",
        "2026-04-14", "2026-04-18", "2026-05-01", "2026-08-15",
        "2026-10-02", "2026-11-05", "2026-12-25",
    ]),
    "lower_window": 0,
    "upper_window": 0,
})


# ════════════════════════════════════════════════════════════
# PHASE 1 CONFIGS
# ════════════════════════════════════════════════════════════

REGIME_CONFIG = {
    "n_components" : 4,
    "covariance_type" : "full",
    "n_iter" : 100,
    "random_state" : 42,
}

ALTERNATIVE_DATA_CONFIG = {
    "fetch_fii_dii" : True,
    "fetch_pcr"     : True,
    "fetch_vix"     : True,
    "fetch_sentiment" : True,
}

LANGGRAPH_CONFIG = {
    "node_timeout_seconds" : 300,
    "max_retries" : 2,
}

FINBERT_MODEL = "ProsusAI/finbert"

WEBSOCKET_CONFIG = {
    "heartbeat_interval_seconds" : 30,
}


# ════════════════════════════════════════════════════════════
# AGENT SEARCH OPTIMIZATION (Factman & rgx)
# ════════════════════════════════════════════════════════════

SEARCH_CONFIG = {
    # Token budgets for advisor queries
    "default_budget": 3000,
    "signal_budget" : 1500,
    "config_budget" : 1000,

    # rgx configurations
    "collapse_threshold": 5,

    # Factman toggle
    "factman_enabled": True,
}


# ════════════════════════════════════════════════════════════
# VALIDATION
# ════════════════════════════════════════════════════════════

def validate_settings() -> bool:
    errors = []

    if not PORTFOLIO_TICKERS:
        errors.append("PORTFOLIO_TICKERS cannot be empty")

    if RISK_AVERSION <= 0:
        errors.append("RISK_AVERSION must be positive")

    if not (0 <= MINIMUM_ALLOCATION <= 1):
        errors.append("MINIMUM_ALLOCATION must be between 0 and 1")

    if not (0 <= MAXIMUM_ALLOCATION <= 1):
        errors.append("MAXIMUM_ALLOCATION must be between 0 and 1")

    if MINIMUM_ALLOCATION > MAXIMUM_ALLOCATION:
        errors.append("MINIMUM_ALLOCATION cannot exceed MAXIMUM_ALLOCATION")

    if len(PORTFOLIO_TICKERS) * MINIMUM_ALLOCATION > 1:
        errors.append(
            f"Impossible constraints: {len(PORTFOLIO_TICKERS)} stocks "
            f"× {MINIMUM_ALLOCATION} min = "
            f"{len(PORTFOLIO_TICKERS) * MINIMUM_ALLOCATION:.2f} > 1.0"
        )

    if not (0 < SIGNAL_CONFIDENCE_THRESHOLD < 1):
        errors.append("SIGNAL_CONFIDENCE_THRESHOLD must be between 0 and 1")

    if errors:
        raise ValueError("DhanNiti config errors:\n" + "\n".join(f"  • {e}" for e in errors))

    return True

PROPHET_PARAMS = {
    "yearly_seasonality"      : True,
    "weekly_seasonality"      : True,
    "daily_seasonality"       : False,
    "changepoint_prior_scale" : 0.05,
    "seasonality_prior_scale" : 10.0,
    "uncertainty_samples"     : 0,
    "stan_backend"            : "CMDSTANPY",
}

validate_settings()