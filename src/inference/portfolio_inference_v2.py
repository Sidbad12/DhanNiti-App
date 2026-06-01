"""
DhanNiti V2 — SAC Portfolio Inference

Single-stock ticker-agnostic SAC agent that scores each ticker independently
(allocation 0→1) and then normalises across the active portfolio universe.

Aligns with:
  - src/agent/gym_env_v2.py  (NSEStockGymEnv, 81-dim observation)
  - src/data/feature_builder.py (build_v2_features → V2_STRICT_STATIC_COLUMNS)
  - scripts/evaluate_v2.py  (evaluation reference implementation)
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_VERSION_V2 = "v2"
DEFAULT_V2_SAC_PATH = "models/v2/v2_sac_final.zip"

# Held-out tickers that the V2 agent *was* validated on.
# At inference time, we score whatever tickers the caller requests.
V2_PORTFOLIO_UNIVERSE: list[str] = [
    "BAJAJFINSV.NS", "MPHASIS.NS",    "OBEROIRLTY.NS", "APOLLOTYRE.NS",
    "SUVEN.NS",      "JYOTHYLAB.NS",  "GRINDWELL.NS",  "IPCALAB.NS",
    "UJJIVANSFB.NS", "EMAMILTD.NS",
]


def _load_sac_model(model_path: str):
    """Load the SAC checkpoint — lazy import to avoid heavy SB3 at import time."""
    from stable_baselines3 import SAC
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"SAC model checkpoint not found at: {model_path}\n"
            "Download v2_sac_final.zip from Kaggle and place it under models/v2/."
        )
    model = SAC.load(model_path)
    logger.info("SAC model loaded from %s", model_path)
    return model


def _build_v2_observation(ticker: str, df_features: pd.DataFrame) -> np.ndarray | None:
    """
    Build the 81-dim observation for a single ticker at the LATEST available bar.

    Mirrors exactly what evaluate_v2.py does:
      1. Reset env (step=0, random_start=False)
      2. Advance current_step to the last available bar
      3. Call _get_observation() which reads V2_STRICT_STATIC_COLUMNS in the
         canonical order defined by feature_builder.py + appends 3 dynamic
         position-context features (current_position=0, days=0, pnl=0).

    Returns None if the feature matrix is too thin to be reliable.
    """
    from src.agent.gym_env_v2 import NSEStockGymEnv

    if df_features is None or df_features.empty:
        logger.warning("Empty feature matrix for %s — skipping.", ticker)
        return None

    if len(df_features) < 2:
        logger.warning("Feature matrix for %s has < 2 rows — skipping.", ticker)
        return None

    env = NSEStockGymEnv(
        ticker=ticker,
        features_dict={ticker: df_features},
        random_start=False,
    )
    # Reset initialises internal state (position=0, days=0, pnl=0) at step 0.
    env.reset(options={"random_start": False})
    # Advance to the very last bar — this is the "today" inference point.
    env.current_step = len(env.df) - 1
    # _get_observation() is the canonical method (NOT _get_obs).
    # It slices df.iloc[current_step][V2_STRICT_STATIC_COLUMNS] then appends
    # the 3 dynamic position-context scalars.
    obs = env._get_observation()
    return obs


def predict_single_ticker_allocation(
    model,
    ticker: str,
    df_features: pd.DataFrame,
) -> float:
    """
    Run SAC deterministic inference for a single ticker.
    Returns a raw allocation score in [0, 1].
    """
    obs = _build_v2_observation(ticker, df_features)
    if obs is None:
        return 0.0
    action, _ = model.predict(obs, deterministic=True)
    # action shape: (1,) — clamp to valid range
    return float(np.clip(action[0], 0.0, 1.0))


def predict_v2_portfolio_weights(
    tickers: Sequence[str] | None = None,
    as_of_date: date | datetime | str | None = None,
    model_path: str = DEFAULT_V2_SAC_PATH,
    features_dict: dict[str, pd.DataFrame] | None = None,
    min_allocation_threshold: float = 0.02,
    start_date: str = "2023-01-01",
) -> dict[str, float]:
    """
    Run V2 SAC inference over a portfolio universe and return normalised weights.

    Each ticker is scored independently (allocation ∈ [0,1]).  Tickers below
    `min_allocation_threshold` after normalisation are zeroed and the remainder
    is re-normalised.

    Args:
        tickers:     Universe to score. Defaults to V2_PORTFOLIO_UNIVERSE.
        as_of_date:  Cut-off date for feature history; defaults to today.
        model_path:  Path to the SAC .zip checkpoint.
        features_dict: Pre-built V2 feature DataFrames.  If None the function
                       builds them via `build_v2_features`.
        min_allocation_threshold: Tickers with a normalised weight below this
                       fraction are treated as "cash out" and zeroed.

    Returns:
        Mapping {ticker: normalised_weight}.  Weights sum to 1.0 (or 0 if all
        tickers fail feature building).
    """
    from src.data.feature_builder import build_v2_features

    universe = list(tickers or V2_PORTFOLIO_UNIVERSE)

    # Coerce as_of_date to a string
    if as_of_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    elif isinstance(as_of_date, (date, datetime)):
        end_date = as_of_date.strftime("%Y-%m-%d")
    else:
        end_date = str(as_of_date)

    model = _load_sac_model(model_path)

    raw_scores: dict[str, float] = {}
    for ticker in universe:
        try:
            if features_dict and ticker in features_dict and features_dict[ticker] is not None:
                df_feat = features_dict[ticker]
            else:
                logger.info("Building V2 features for %s (as_of=%s)…", ticker, end_date)
                df_feat = build_v2_features(ticker, start_date=start_date, is_historical=True)

            score = predict_single_ticker_allocation(model, ticker, df_feat)
            raw_scores[ticker] = score
            logger.info("  %s → raw SAC score %.4f", ticker, score)

        except Exception:
            logger.exception("SAC scoring failed for %s — assigning 0.", ticker)
            raw_scores[ticker] = 0.0

    total = sum(raw_scores.values())
    if total < 1e-9:
        logger.warning("All raw SAC scores are zero — returning equal weights.")
        n = len(universe)
        return {t: 1.0 / n for t in universe}

    # Normalise
    normalised: dict[str, float] = {t: v / total for t, v in raw_scores.items()}

    # Zero out tickers below threshold and re-normalise
    filtered = {t: w for t, w in normalised.items() if w >= min_allocation_threshold}
    if not filtered:
        filtered = normalised  # fallback: nothing passes threshold, keep all

    total_filtered = sum(filtered.values())
    final_weights = {t: round(w / total_filtered, 6) for t, w in filtered.items()}

    # Add zero-weighted tickers back (excluded from re-norm)
    for t in universe:
        if t not in final_weights:
            final_weights[t] = 0.0

    logger.info(
        "V2 SAC inference done — active positions=%d  weight_sum=%.6f",
        sum(1 for w in final_weights.values() if w > 0),
        sum(final_weights.values()),
    )
    return final_weights
