"""
V1 portfolio inference — single path for API and smoke tests.

Must stay aligned with:
  - scripts/train_rl_agent.py (extract_data → build_full_feature_matrix)
  - src/agent/rl_agent.py (NSEPortfolioGymEnv._get_observation → predict → _normalize_weights)

Do not add V2 observation tiers (VIX matrix, FinBERT, etc.) here — Phase B only.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.agent.gym_env import NSEPortfolioGymEnv
from src.agent.rl_agent import RLPortfolioAgent
from src.data.extractor import extract_data
from src.features.pipeline import build_full_feature_matrix
from src.settings import PORTFOLIO_TICKERS, START_DATE

logger = logging.getLogger(__name__)

MODEL_VERSION_V1 = "v1"
DEFAULT_MODEL_NAME = "ppo_dhanniti"


def _coerce_as_of_date(as_of_date: date | datetime | str | None) -> str:
    if as_of_date is None:
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(as_of_date, datetime):
        return as_of_date.strftime("%Y-%m-%d")
    if isinstance(as_of_date, date):
        return as_of_date.strftime("%Y-%m-%d")
    return str(as_of_date)


def build_features_dict(
    tickers: list[str] | None = None,
    as_of_date: date | datetime | str | None = None,
    start_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Build per-ticker feature matrices exactly as train_rl_agent.py does.

    Args:
        tickers: Symbols to include; defaults to PORTFOLIO_TICKERS.
        as_of_date: End of history window (inclusive).
        start_date: History start; defaults to settings START_DATE.

    Returns:
        features_dict for gym / PPO inference.
    """
    universe = list(tickers or PORTFOLIO_TICKERS)
    end = _coerce_as_of_date(as_of_date)
    start = start_date or START_DATE

    logger.info("Extracting data for %d tickers (%s → %s)", len(universe), start, end)
    raw_data = extract_data(universe, start, end)

    logger.info("Building full feature matrix (add_labels=False)")
    features_dict = build_full_feature_matrix(raw_data, add_labels=False)

    missing = [t for t in universe if t not in features_dict or features_dict[t].empty]
    if missing:
        logger.warning("No feature rows for tickers: %s", missing)

    return features_dict


def _inference_env(features_dict: dict[str, pd.DataFrame]) -> NSEPortfolioGymEnv:
    """Gym env configured for latest-bar inference (matches rl_agent.predict_weights)."""
    env = NSEPortfolioGymEnv(features_dict=features_dict)
    env.dates = env.all_dates.copy()
    env.current_step = len(env.dates) - 1
    return env


def get_observation_for_features(features_dict: dict[str, pd.DataFrame]) -> np.ndarray:
    """
    Observation vector used by PPO at inference — must match rl_agent.predict_weights.
    """
    env = _inference_env(features_dict)
    return env._get_observation()


def predict_portfolio_weights(
    tickers: list[str] | None = None,
    as_of_date: date | datetime | str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    features_dict: dict[str, pd.DataFrame] | None = None,
) -> dict[str, float]:
    """
    Run V1 PPO inference and return normalized portfolio weights.

    Args:
        tickers: Universe; defaults to PORTFOLIO_TICKERS.
        as_of_date: As-of date for feature history.
        model_name: Checkpoint stem under models/ (without .zip).
        features_dict: Pre-built features; if None, built via build_features_dict.

    Returns:
        Mapping ticker → weight (sums to ~1.0 when model checkpoint exists).
    """
    universe = list(tickers or PORTFOLIO_TICKERS)
    fd = features_dict if features_dict is not None else build_features_dict(
        tickers=universe, as_of_date=as_of_date
    )

    agent = RLPortfolioAgent()
    weights = agent.predict_weights(fd, model_name=model_name)

    logger.info(
        "Inference complete model=%s tickers=%d weight_sum=%.6f",
        model_name,
        len(weights),
        sum(weights.values()),
    )
    return weights
