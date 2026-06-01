"""
Feature assembly pipeline combining pandas_ta technicals and Prophet features.
"""

import logging
import pandas as pd

from src.features.technical import build_features_for_portfolio
from src.features.prophet_decomp import extract_prophet_features

logger = logging.getLogger(__name__)


def build_full_feature_matrix(
    portfolio_data: dict[str, pd.DataFrame],
    add_labels: bool = True
) -> dict[str, pd.DataFrame]:
    """
    Build complete feature matrices for all tickers in the portfolio.
    Combines pandas_ta technical indicators with Prophet decomposition.

    Args:
        portfolio_data: Dict mapping ticker to historical DataFrame (OHLCV)
        add_labels: Whether to append target labels (for training)

    Returns:
        Dict mapping ticker to fully enriched feature DataFrame
    """
    feature_matrices = {}

    # 1. Build technical indicators for all tickers
    logger.info("Building technical indicator features...")
    tech_features = build_features_for_portfolio(portfolio_data, add_labels=add_labels)

    # 2. Append Prophet features for each ticker
    for ticker, df_tech in tech_features.items():
        try:
            logger.debug(f"Extracting Prophet features for {ticker}...")
            # Extract prophet features using the Close price series
            # Ensure index is datetime for Prophet
            price_series = df_tech["Close"].copy()
            price_series.index = pd.to_datetime(price_series.index)
            
            df_prophet = extract_prophet_features(price_series)
            
            # Align indices back to original
            df_prophet.index = df_tech.index
            
            # Merge
            df_combined = pd.concat([df_tech, df_prophet], axis=1)
            
            feature_matrices[ticker] = df_combined
            logger.info(f"{ticker}: Successfully combined {df_combined.shape[1]} features.")
            
        except Exception as e:
            logger.error(f"Failed to build full feature matrix for {ticker}: {e}")
            # Fallback to just technicals
            feature_matrices[ticker] = df_tech

    return feature_matrices
