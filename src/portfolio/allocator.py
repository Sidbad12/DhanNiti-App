"""Allocation router routing between Reinforcement Learning PPO agent and Markowitz baselines."""

import logging
import pandas as pd

from src.portfolio.markowitz import optimize_portfolio_mean_variance
from src.agent.rl_agent import RLPortfolioAgent

logger = logging.getLogger(__name__)


def allocate_portfolio(
    data_dict: dict[str, pd.DataFrame],
    rl_agent: RLPortfolioAgent,
    features_dict: dict[str, pd.DataFrame] = None,
    mode: str = "blend",
    rl_model_name: str = "ppo_dhanniti"
) -> dict[str, float]:
    """
    Route and allocate portfolio weights based on the selected mode.

    Args:
        data_dict: Dict of historical price DataFrames
        rl_agent: Trained RLPortfolioAgent instance
        features_dict: Optional dict of complete feature DataFrames (needed for RL)
        mode: Allocation mode ('markowitz', 'agent', 'blend')
        rl_model_name: Name of the RL agent checkpoint

    Returns:
        Dict mapping ticker to optimal allocation weight
    """
    tickers = sorted(list(data_dict.keys()))
    num_assets = len(tickers)

    # 1. Compute Markowitz baseline weights
    logger.info("Computing baseline Markowitz Mean-Variance weights...")
    try:
        markowitz_weights = optimize_portfolio_mean_variance(data_dict)
    except Exception as e:
        logger.error(f"Markowitz optimization failed: {e}. Falling back to equal weights.")
        markowitz_weights = {ticker: 1.0 / num_assets for ticker in tickers}

    # If pure markowitz mode is selected, return immediately
    if mode == "markowitz":
        return markowitz_weights

    # 2. Compute RL Agent weights
    logger.info("Computing RL PPO Agent weights...")
    if features_dict is None:
        logger.warning("No features provided for RL Agent, falling back to Markowitz baseline.")
        return markowitz_weights

    try:
        agent_weights = rl_agent.predict_weights(features_dict, model_name=rl_model_name)
    except Exception as e:
        logger.error(f"RL agent weights prediction failed: {e}. Falling back to Markowitz baseline.")
        return markowitz_weights

    # If pure agent mode is selected, return immediately
    if mode == "agent":
        return agent_weights

    # 3. Blended allocation (50% Markowitz + 50% RL PPO Agent)
    logger.info("Blending Markowitz and RL Agent allocations (50/50 approach)...")
    blended_weights = {}
    for ticker in tickers:
        m_w = markowitz_weights.get(ticker, 1.0 / num_assets)
        a_w = agent_weights.get(ticker, 1.0 / num_assets)
        blended_weights[ticker] = 0.5 * m_w + 0.5 * a_w

    # Re-normalize to sum to exactly 1.0
    total_w = sum(blended_weights.values())
    if total_w > 0:
        blended_weights = {t: w / total_w for t, w in blended_weights.items()}

    return blended_weights
