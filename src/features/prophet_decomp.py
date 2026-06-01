"""Prophet-based time series decomposition as feature extractor."""

import logging
import pandas as pd
from prophet import Prophet

from src.settings import INDIAN_MARKET_HOLIDAYS, PROPHET_PARAMS

logger = logging.getLogger(__name__)


def extract_prophet_features(price_series: pd.Series) -> pd.DataFrame:
    """
    Fit a Prophet model on the historical price series and extract decomposed components
    (trend, weekly, yearly, holidays, yhat) as features.

    Args:
        price_series: Historical price series with DatetimeIndex

    Returns:
        DataFrame with columns ['Prophet_Trend', 'Prophet_Weekly', 'Prophet_Yearly', 
                               'Prophet_Holidays', 'Prophet_Forecast'] aligned with original series index.
    """
    try:
        # Prepare data for Prophet
        df_prophet = pd.DataFrame({
            "ds": pd.to_datetime(price_series.index),
            "y": price_series.values
        })

        # Filter Indian holidays to relevant date range
        start_date = price_series.index.min()
        end_date = price_series.index.max()
        holidays = INDIAN_MARKET_HOLIDAYS.copy()
        holidays = holidays[
            (holidays["ds"] >= pd.to_datetime(start_date))
            & (holidays["ds"] <= pd.to_datetime(end_date))
        ]

        # Configure Prophet
        prophet_params = PROPHET_PARAMS.copy()
        if not holidays.empty:
            prophet_params["holidays"] = holidays

        # Fit model
        model = Prophet(**prophet_params)
        model.fit(df_prophet)

        # Predict historical values
        forecast = model.predict(df_prophet)

        # Create output DataFrame
        features = pd.DataFrame(index=price_series.index)
        features["Prophet_Trend"] = forecast["trend"].values
        
        # Capture seasonality features if present in forecast
        features["Prophet_Weekly"] = forecast["weekly"].values if "weekly" in forecast.columns else 0.0
        features["Prophet_Yearly"] = forecast["yearly"].values if "yearly" in forecast.columns else 0.0
        features["Prophet_Holidays"] = forecast["holidays"].values if "holidays" in forecast.columns else 0.0
        features["Prophet_Forecast"] = forecast["yhat"].values
        features["Prophet_Upper"] = forecast["yhat_upper"].values if "yhat_upper" in forecast.columns else forecast["yhat"].values
        features["Prophet_Lower"] = forecast["yhat_lower"].values if "yhat_lower" in forecast.columns else forecast["yhat"].values

        # Ratio features to compare current price with Prophet prediction
        features["Prophet_Price_Ratio"] = price_series.values / (forecast["yhat"].values + 1e-8)

        return features

    except Exception as e:
        logger.error(f"Error in Prophet decomposition: {e}")
        # Return default values in case of failure
        features = pd.DataFrame(index=price_series.index)
        features["Prophet_Trend"] = price_series.values
        features["Prophet_Weekly"] = 0.0
        features["Prophet_Yearly"] = 0.0
        features["Prophet_Holidays"] = 0.0
        features["Prophet_Forecast"] = price_series.values
        features["Prophet_Upper"] = price_series.values
        features["Prophet_Lower"] = price_series.values
        features["Prophet_Price_Ratio"] = 1.0
        return features
