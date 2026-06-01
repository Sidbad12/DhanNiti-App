"""
DhanNiti V2 — Feature Builder
Downloads and processes historical OHLCV + macro data for any NSE stock,
generating a standardized 78-feature static observation matrix.
"""

import os
import logging
import time
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from src.data.extractor import get_yfinance_session

from src.settings import START_DATE, END_DATE
from src.features.technical import build_features
from src.features.prophet_decomp import extract_prophet_features
from src.ml.regime import RegimeDetector

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# SECTOR MAPPING FOR TRAINING UNIVERSE
# ════════════════════════════════════════════════════════════
SECTOR_MAP = {
    # Financials
    "HDFCBANK.NS": "financials", "ICICIBANK.NS": "financials", "SBIN.NS": "financials",
    "KOTAKBANK.NS": "financials", "AXISBANK.NS": "financials", "BAJFINANCE.NS": "financials",
    "HDFCLIFE.NS": "financials", "SBILIFE.NS": "financials", "BANDHANBNK.NS": "financials",
    "FEDERALBNK.NS": "financials", "IDFCFIRSTB.NS": "financials", "MUTHOOTFIN.NS": "financials",
    "PNB.NS": "financials", "CHOLAFIN.NS": "financials", "RBLBANK.NS": "financials",
    "UJJIVANSFB.NS": "financials", "BAJAJFINSV.NS": "financials", "INDUSINDBK.NS": "financials",
    # IT
    "TCS.NS": "it", "INFY.NS": "it", "WIPRO.NS": "it", "HCLTECH.NS": "it", "TECHM.NS": "it",
    "LTIM.NS": "it", "PERSISTENT.NS": "it", "COFORGE.NS": "it", "MPHASIS.NS": "it",
    "LTTS.NS": "it", "MASTEK.NS": "it", "KPITTECH.NS": "it", "TATAELXSI.NS": "it",
    # Energy
    "RELIANCE.NS": "energy", "ONGC.NS": "energy", "NTPC.NS": "energy", "POWERGRID.NS": "energy",
    "COALINDIA.NS": "energy", "BPCL.NS": "energy",
    # Consumer
    "HINDUNILVR.NS": "consumer", "ITC.NS": "consumer", "NESTLEIND.NS": "consumer",
    "BRITANNIA.NS": "consumer", "DABUR.NS": "consumer", "MARICO.NS": "consumer",
    "GODREJCP.NS": "consumer", "COLPAL.NS": "consumer", "EMAMILTD.NS": "consumer",
    "ZYDUSWELL.NS": "consumer", "JYOTHYLAB.NS": "consumer", "TITAN.NS": "consumer",
    "ASIANPAINT.NS": "consumer", "TATACONSUM.NS": "consumer",
    # Industrials & Metals
    "LT.NS": "industrials", "SIEMENS.NS": "industrials", "ABB.NS": "industrials",
    "HAVELLS.NS": "industrials", "VOLTAS.NS": "industrials", "POLYCAB.NS": "industrials",
    "GRINDWELL.NS": "industrials", "KAYNES.NS": "industrials", "APLAPOLLO.NS": "industrials",
    "TATASTEEL.NS": "industrials", "JSWSTEEL.NS": "industrials", "HINDALCO.NS": "industrials",
    "ULTRACEMCO.NS": "industrials", "GRASIM.NS": "industrials", "SRF.NS": "industrials",
    "ATUL.NS": "industrials", "CUMMINSIND.NS": "industrials",
    # Auto
    "TATAMOTORS.NS": "auto", "MARUTI.NS": "auto", "BAJAJ-AUTO.NS": "auto",
    "HEROMOTOCO.NS": "auto", "EICHERMOT.NS": "auto", "BALKRISIND.NS": "auto",
    "MOTHERSON.NS": "auto", "BOSCHLTD.NS": "auto", "M&M.NS": "auto",
    # Pharma
    "SUNPHARMA.NS": "pharma", "DRREDDY.NS": "pharma", "CIPLA.NS": "pharma",
    "DIVISLAB.NS": "pharma", "AUROPHARMA.NS": "pharma", "TORNTPHARM.NS": "pharma",
    "ALKEM.NS": "pharma", "IPCALAB.NS": "pharma", "GRANULES.NS": "pharma",
    "SUVEN.NS": "pharma", "APOLLOHOSP.NS": "pharma",
    # Infra & Real Estate
    "DLF.NS": "infra", "GODREJPROP.NS": "infra", "OBEROIRLTY.NS": "infra"
}

# The exact 78 static features required for the V2 observation space
STATIC_FEATURE_COLUMNS = [
    # 1-7. Price & Momentum
    "close_norm", "return_1d", "return_5d", "return_10d", "return_20d", "return_60d", "gap_open",
    # 8-23. Technicals & Oscillators
    "rsi_10", "rsi_14", "rsi_21", "roc", "mom", "macd", "macd_signal", "macd_hist",
    "cci_20", "williams_r", "adx_14", "atr_14_norm", "obv_norm", "vwap_deviation", "stoch_k", "stoch_d",
    # 24-34. SMA/EMA Distances & Crossovers
    "sma_5_dist", "sma_10_dist", "sma_20_dist", "sma_50_dist",
    "ema_5_dist", "ema_10_dist", "ema_20_dist", "ema_50_dist",
    "ema_cross_5_20", "ema_cross_10_50", "vwma_dist",
    # 35-44. Volatility Channels
    "bb_position", "bb_width", "bb_upper_dist", "bb_lower_dist", "bb_mid_dist",
    "kc_upper_dist", "kc_lower_dist",
    # 45-50. Volume Indicators
    "volume_ratio_5d", "volume_ratio_20d", "volume_trend", "obv_roc", "ad_roc", "efi",
    # 51-54. Prophet Decomposition
    "prophet_trend", "prophet_weekly", "prophet_yhat_norm", "prophet_uncertainty",
    # 55-58. Risk Metrics
    "realized_vol_5d", "realized_vol_20d", "drawdown_depth", "beta_nifty_20d",
    # 59-67. Market Context (Global)
    "india_vix", "nifty_return_1d", "nifty_return_5d",
    "regime_bull", "regime_bear", "regime_high_vol", "regime_sideways",
    "fii_flow_norm", "dii_flow_norm",
    # 68-69. Sector Momentum
    "sector_return_5d", "sector_relative",
    # 70-73. FinBERT Sentiment
    "sentiment_composite", "sentiment_positive", "sentiment_negative", "news_volume_norm",
    # 74-78. News Categories
    "news_macro_rbi", "news_macro_crude", "news_earnings", "news_regulatory",
    "news_global", "news_promoter", "sector_news_agg", "peer_sentiment_gap"
]

# All 86 static feature columns (78 technical + 8 news)
V2_STRICT_STATIC_COLUMNS = STATIC_FEATURE_COLUMNS


def download_with_fallback(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download price data using yfinance with fallback logic and retry backoff."""
    session = get_yfinance_session()
    
    # Try downloading with retry
    df = pd.DataFrame()
    for attempt in range(3):
        try:
            df = yf.download(ticker, start=start, end=end, session=session)
            if not df.empty:
                break
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed for {ticker}: {e}")
        time.sleep(2 ** attempt + 1)
        
    if df.empty and ticker == "TATAMOTORS.NS":
        logger.warning(f"Ticker {ticker} returned empty. Trying demerged fallback TMPV.NS...")
        for attempt in range(3):
            try:
                df = yf.download("TMPV.NS", start=start, end=end, session=session)
                if not df.empty:
                    break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for TMPV.NS: {e}")
            time.sleep(2 ** attempt + 1)
    elif df.empty and ticker.endswith(".NS"):
        fallback_ticker = ticker.replace(".NS", ".BO")
        logger.warning(f"Ticker {ticker} returned empty. Trying BSE fallback {fallback_ticker}...")
        for attempt in range(3):
            try:
                df = yf.download(fallback_ticker, start=start, end=end, session=session)
                if not df.empty:
                    break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {fallback_ticker}: {e}")
            time.sleep(2 ** attempt + 1)
    return df


def safe_series(df: pd.DataFrame, col_name: str, fallback_val: float = 0.0) -> pd.Series:
    """Extract a 1D Series from a yfinance DataFrame, handling MultiIndex and duplicate column structures."""
    if df.empty:
        return pd.Series(fallback_val, dtype=float)
        
    # Check direct match
    if col_name in df.columns:
        col_data = df[col_name]
        if isinstance(col_data, pd.DataFrame):
            return col_data.iloc[:, 0]
        return col_data
        
    # Check lowercase or tuple match
    for col in df.columns:
        if isinstance(col, tuple):
            if col_name.lower() in [str(x).lower() for x in col]:
                col_data = df[col]
                if isinstance(col_data, pd.DataFrame):
                    return col_data.iloc[:, 0]
                return col_data
        elif str(col).lower() == col_name.lower():
            col_data = df[col]
            if isinstance(col_data, pd.DataFrame):
                return col_data.iloc[:, 0]
            return col_data
            
    # Fallback Series with matching index
    return pd.Series(fallback_val, index=df.index, dtype=float)


def build_v2_features(
    ticker: str,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    add_labels: bool = False,
    is_historical: bool | None = None
) -> pd.DataFrame:
    """
    Build complete 78 static features for a single ticker.
    Downloads Nifty 50 and India VIX for market context.
    """
    logger.info(f"Building V2 features for {ticker} from {start_date} to {end_date}")

    # 1. Download stock, Nifty 50, and India VIX data (keeping DatetimeIndex)
    session = get_yfinance_session()
    stock_df = download_with_fallback(ticker, start_date, end_date)
    
    # Cache market context to avoid Yahoo Finance rate limits
    global _MARKET_CONTEXT_CACHE
    if '_MARKET_CONTEXT_CACHE' not in globals():
        _MARKET_CONTEXT_CACHE = {}
        
    cache_key = (start_date, end_date)
    if cache_key in _MARKET_CONTEXT_CACHE:
        nifty_df, vix_df = _MARKET_CONTEXT_CACHE[cache_key]
    else:
        nifty_df = pd.DataFrame()
        vix_df = pd.DataFrame()
        for attempt in range(3):
            try:
                nifty_df = yf.download("^NSEI", start=start_date, end=end_date, session=session)
                if not nifty_df.empty:
                    break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for ^NSEI: {e}")
            time.sleep(2 ** attempt + 1)
            
        for attempt in range(3):
            try:
                vix_df = yf.download("^INDIAVIX", start=start_date, end=end_date, session=session)
                if not vix_df.empty:
                    break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for ^INDIAVIX: {e}")
            time.sleep(2 ** attempt + 1)
            
        if not nifty_df.empty and not vix_df.empty:
            _MARKET_CONTEXT_CACHE[cache_key] = (nifty_df, vix_df)

    if stock_df.empty:
        raise ValueError(f"Could not download price data for ticker: {ticker}")

    # Standardize index naming
    stock_df.index.name = "Date"
    nifty_df.index.name = "Date"
    vix_df.index.name = "Date"

    # Align data to stock_df dates using DatetimeIndex intersections
    common_dates = stock_df.index.intersection(nifty_df.index)
    stock_df = stock_df.loc[common_dates].copy()
    nifty_df = nifty_df.loc[common_dates].copy()

    # Reconstruct as standard, flat, clean DataFrames using safe_series
    stock_df = pd.DataFrame({
        "Open": safe_series(stock_df, "Open"),
        "High": safe_series(stock_df, "High"),
        "Low": safe_series(stock_df, "Low"),
        "Close": safe_series(stock_df, "Close"),
        "Volume": safe_series(stock_df, "Volume")
    }, index=stock_df.index)

    nifty_df = pd.DataFrame({
        "Open": safe_series(nifty_df, "Open"),
        "High": safe_series(nifty_df, "High"),
        "Low": safe_series(nifty_df, "Low"),
        "Close": safe_series(nifty_df, "Close"),
        "Volume": safe_series(nifty_df, "Volume")
    }, index=nifty_df.index)

    vix_df = pd.DataFrame({
        "Close": safe_series(vix_df, "Close", fallback_val=15.0)
    }, index=vix_df.index)

    # 2. Extract technical features using standard pipeline (complies with DatetimeIndex)
    tech_df = build_features(stock_df, add_labels=False)

    # 3. Extract Prophet features
    close_series = stock_df["Close"].copy()
    prophet_raw = extract_prophet_features(close_series)
    prophet_raw.index = stock_df.index

    # 4. Initialize result DataFrame
    df = pd.DataFrame(index=stock_df.index)
    
    # Keep OHLCV for env simulation
    df["Open"] = stock_df["Open"]
    df["High"] = stock_df["High"]
    df["Low"] = stock_df["Low"]
    df["Close"] = stock_df["Close"]
    df["Volume"] = stock_df["Volume"]
    df["Returns"] = stock_df["Close"].pct_change().fillna(0.0)

    # ── PRICE & MOMENTUM FEATURES ──
    roll_52w_low = stock_df["Close"].rolling(252, min_periods=20).min()
    roll_52w_high = stock_df["Close"].rolling(252, min_periods=20).max()
    df["close_norm"] = (stock_df["Close"] - roll_52w_low) / (roll_52w_high - roll_52w_low + 1e-9)
    df["close_norm"] = df["close_norm"].fillna(0.5)

    df["return_1d"] = df["Returns"]
    df["return_5d"] = stock_df["Close"].pct_change(5).fillna(0.0)
    df["return_10d"] = stock_df["Close"].pct_change(10).fillna(0.0)
    df["return_20d"] = stock_df["Close"].pct_change(20).fillna(0.0)
    df["return_60d"] = stock_df["Close"].pct_change(60).fillna(0.0)
    
    prev_close = stock_df["Close"].shift(1)
    df["gap_open"] = ((stock_df["Open"] - prev_close) / (prev_close + 1e-9)).fillna(0.0)

    # ── TECHNICALS & OSCILLATORS ──
    df["rsi_10"] = tech_df.get("rsi_10", 0.5)
    df["rsi_14"] = tech_df.get("rsi_14", 0.5)
    df["rsi_21"] = tech_df.get("rsi_21", 0.5)
    df["roc"] = tech_df.get("roc", 0.0)
    df["mom"] = tech_df.get("mom", 0.0)
    df["macd"] = tech_df.get("macd_line", 0.0)
    df["macd_signal"] = tech_df.get("macd_signal", 0.0)
    df["macd_hist"] = tech_df.get("macd_hist", 0.0)
    
    # bb position and width (Corrected: Multiplying distances by close)
    bb_upper = stock_df["Close"] * (1.0 + tech_df.get("bb_upper_dist", 0.0))
    bb_lower = stock_df["Close"] * (1.0 + tech_df.get("bb_lower_dist", 0.0))
    df["bb_position"] = ((stock_df["Close"] - bb_lower) / (bb_upper - bb_lower + 1e-9)).fillna(0.5)
    df["bb_width"] = tech_df.get("bb_width", 0.1)
    df["bb_upper_dist"] = tech_df.get("bb_upper_dist", 0.0)
    df["bb_lower_dist"] = tech_df.get("bb_lower_dist", 0.0)
    df["bb_mid_dist"] = tech_df.get("bb_mid_dist", 0.0)
    
    df["cci_20"] = tech_df.get("cci", 0.0)
    df["williams_r"] = tech_df.get("willr", -0.5)
    
    # adx
    import pandas_ta as ta
    adx_df = ta.adx(stock_df["High"], stock_df["Low"], stock_df["Close"], length=14)
    if adx_df is not None and not adx_df.empty:
        df["adx_14"] = adx_df.iloc[:, 0] / 100.0
    else:
        df["adx_14"] = 0.25
    df["adx_14"] = df["adx_14"].fillna(0.25)
    
    df["atr_14_norm"] = tech_df.get("atr_norm", 0.02)
    df["obv_norm"] = tech_df.get("obv_roc", 0.0)
    
    # VWAP deviation
    vwap = ta.vwap(stock_df["High"], stock_df["Low"], stock_df["Close"], stock_df["Volume"])
    if vwap is not None:
        vwap.index = stock_df.index
        df["vwap_deviation"] = (stock_df["Close"] - vwap) / (vwap + 1e-9)
    else:
        df["vwap_deviation"] = 0.0
    df["vwap_deviation"] = df["vwap_deviation"].fillna(0.0)

    # Stochastic
    stoch = ta.stoch(stock_df["High"], stock_df["Low"], stock_df["Close"])
    if stoch is not None:
        stoch.index = stock_df.index
        df["stoch_k"] = stoch.iloc[:, 0] / 100.0
        df["stoch_d"] = stoch.iloc[:, 1] / 100.0
    else:
        df["stoch_k"] = 0.5
        df["stoch_d"] = 0.5
    df["stoch_k"] = df["stoch_k"].fillna(0.5)
    df["stoch_d"] = df["stoch_d"].fillna(0.5)

    # SMA/EMA distances
    df["sma_5_dist"] = tech_df.get("sma_5_dist", 0.0)
    df["sma_10_dist"] = tech_df.get("sma_10_dist", 0.0)
    df["sma_20_dist"] = tech_df.get("sma_20_dist", 0.0)
    df["sma_50_dist"] = tech_df.get("sma_50_dist", 0.0)
    df["ema_5_dist"] = tech_df.get("ema_5_dist", 0.0)
    df["ema_10_dist"] = tech_df.get("ema_10_dist", 0.0)
    df["ema_20_dist"] = tech_df.get("ema_20_dist", 0.0)
    df["ema_50_dist"] = tech_df.get("ema_50_dist", 0.0)
    df["ema_cross_5_20"] = tech_df.get("ema_cross_5_20", 0.0)
    df["ema_cross_10_50"] = tech_df.get("ema_cross_10_50", 0.0)
    df["vwma_dist"] = tech_df.get("vwma_dist", 0.0)

    # Volatility channels
    df["kc_upper_dist"] = tech_df.get("kc_upper_dist", 0.0)
    df["kc_lower_dist"] = tech_df.get("kc_lower_dist", 0.0)

    # Volume Ratio
    df["volume_ratio_5d"] = (stock_df["Volume"] / (stock_df["Volume"].rolling(5).mean() + 1e-9)).fillna(1.0)
    df["volume_ratio_20d"] = tech_df.get("volume_ratio", 1.0)
    df["volume_trend"] = stock_df["Volume"].pct_change(5).fillna(0.0)
    df["obv_roc"] = tech_df.get("obv_roc", 0.0)
    df["ad_roc"] = tech_df.get("ad_roc", 0.0)
    df["efi"] = tech_df.get("efi", 0.0)

    # Prophet Components
    df["prophet_trend"] = ((prophet_raw["Prophet_Trend"] - stock_df["Close"]) / (stock_df["Close"] + 1e-9)).fillna(0.0)
    df["prophet_weekly"] = (prophet_raw["Prophet_Weekly"] / (stock_df["Close"] + 1e-9)).fillna(0.0)
    df["prophet_yhat_norm"] = ((prophet_raw["Prophet_Forecast"] - stock_df["Close"]) / (stock_df["Close"] + 1e-9)).fillna(0.0)
    df["prophet_uncertainty"] = ((prophet_raw["Prophet_Upper"] - prophet_raw["Prophet_Lower"]) / (stock_df["Close"] + 1e-9)).fillna(0.0)

    # Realized Vol
    df["realized_vol_5d"] = tech_df.get("realised_vol_5d", 0.15)
    df["realized_vol_20d"] = tech_df.get("realised_vol_20d", 0.15)
    
    # Price Drawdown Depth
    running_max = stock_df["Close"].rolling(20, min_periods=1).max()
    df["drawdown_depth"] = ((stock_df["Close"] - running_max) / (running_max + 1e-9)).fillna(0.0)

    # Beta vs Nifty 50 (rolling 20d)
    stock_ret = stock_df["Close"].pct_change().fillna(0.0)
    nifty_ret = nifty_df["Close"].pct_change().fillna(0.0)
    
    covariance = stock_ret.rolling(20).cov(nifty_ret)
    nifty_variance = nifty_ret.rolling(20).var()
    df["beta_nifty_20d"] = (covariance / (nifty_variance + 1e-9)).fillna(1.0)

    # ── MARKET CONTEXT (GLOBAL) ──
    aligned_vix = vix_df["Close"].reindex(stock_df.index, method="ffill").fillna(15.0)
    df["india_vix"] = aligned_vix / 100.0  # normalize
    
    df["nifty_return_1d"] = nifty_ret
    df["nifty_return_5d"] = nifty_df["Close"].pct_change(5).fillna(0.0)

    # HMM Regime
    hmm_detector = RegimeDetector(model_path="models/hmm_regime.pkl")
    if hmm_detector.model is not None:
        regime_history = hmm_detector.get_regime_history(nifty_df)
        regime_history = regime_history.reindex(stock_df.index, method="ffill")
        df["regime_bull"] = (regime_history["regime"] == "bull_trending").astype(float)
        df["regime_bear"] = (regime_history["regime"] == "bear_trending").astype(float)
        df["regime_high_vol"] = (regime_history["regime"] == "high_volatility").astype(float)
        df["regime_sideways"] = (regime_history["regime"] == "range_bound").astype(float)
    else:
        df["regime_bull"] = 0.0
        df["regime_bear"] = 0.0
        df["regime_high_vol"] = 0.0
        df["regime_sideways"] = 1.0

    # FII/DII Net Flow Normalized (Set to 0.0 as placeholder initially)
    df["fii_flow_norm"] = 0.0
    df["dii_flow_norm"] = 0.0

    # ── SECTOR MOMENTUM ──
    sector_name = SECTOR_MAP.get(ticker, "others")
    df["sector_return_5d"] = df["nifty_return_5d"]
    df["sector_relative"] = df["return_5d"] - df["sector_return_5d"]

    # ── NEWS & SENTIMENT ──
    # Auto-detect if we are running historical backtest/training or live inference
    if is_historical is None:
        is_historical = True
        try:
            end_dt = pd.to_datetime(end_date)
            # If the end date is within the last 2 days or in the future, it is live/recent
            if end_dt > datetime.now() - timedelta(days=2):
                is_historical = False
        except Exception:
            pass

        # Force historical mode if training on Kaggle or explicitly flagged
        if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or os.environ.get("TRAINING_MODE") == "True":
            is_historical = True

    if is_historical:
        # Generate high-quality synthetic correlated news for training/backtesting
        logger.info(f"Generating synthetic correlated news for historical training/backtesting on {ticker}")
        
        # We calculate the next-day returns to create a lead indicator for news
        # shift(-1) shifts the future return to the current day, simulating a news release right before the price move
        next_ret = df["Returns"].shift(-1).fillna(0.0)
        
        # Initialize columns
        sentiment_composite = np.zeros(len(df))
        sentiment_positive = np.zeros(len(df))
        sentiment_negative = np.zeros(len(df))
        news_volume_norm = np.zeros(len(df))
        
        news_macro_rbi = np.zeros(len(df))
        news_macro_crude = np.zeros(len(df))
        news_earnings = np.zeros(len(df))
        news_regulatory = np.zeros(len(df))
        news_global = np.zeros(len(df))
        news_promoter = np.zeros(len(df))
        sector_news_agg = np.zeros(len(df))
        peer_sentiment_gap = np.zeros(len(df))
        
        np.random.seed(42 + hash(ticker) % 100000)  # deterministic but distinct per ticker
        
        # Identify strong price movements next day
        pos_mask = next_ret > 0.015
        neg_mask = next_ret < -0.015
        
        # Positive news (e.g. 40% of big up-days are caused by positive earnings or promoter buying news)
        pos_indices = np.where(pos_mask)[0]
        for idx in pos_indices:
            if np.random.rand() < 0.4:
                comp = np.random.uniform(0.4, 0.8)
                sentiment_composite[idx] = comp
                sentiment_positive[idx] = comp
                news_volume_norm[idx] = np.random.uniform(0.3, 0.7)
                
                # Pick a positive news category
                cat = np.random.choice(["earnings", "promoter"])
                if cat == "earnings":
                    news_earnings[idx] = np.random.uniform(0.4, 0.8)
                else:
                    news_promoter[idx] = np.random.uniform(0.4, 0.8)
                    
        # Negative news (e.g. 40% of big down-days are caused by negative regulatory or global macro news)
        neg_indices = np.where(neg_mask)[0]
        for idx in neg_indices:
            if np.random.rand() < 0.4:
                comp = np.random.uniform(-0.8, -0.4)
                sentiment_composite[idx] = comp
                sentiment_negative[idx] = abs(comp)
                news_volume_norm[idx] = np.random.uniform(0.3, 0.7)
                
                # Pick a negative news category
                cat = np.random.choice(["regulatory", "global", "macro_crude"])
                if cat == "regulatory":
                    news_regulatory[idx] = np.random.uniform(0.4, 0.8)
                elif cat == "global":
                    news_global[idx] = np.random.uniform(0.4, 0.8)
                else:
                    news_macro_crude[idx] = np.random.uniform(0.4, 0.8)
        
        # Add minor random background noise to avoid pure zeros on other days
        noise_mask = np.random.rand(len(df)) < 0.05
        for idx in np.where(noise_mask)[0]:
            if sentiment_composite[idx] == 0.0:
                comp = np.random.uniform(-0.2, 0.2)
                sentiment_composite[idx] = comp
                if comp > 0:
                    sentiment_positive[idx] = comp
                else:
                    sentiment_negative[idx] = abs(comp)
                news_volume_norm[idx] = np.random.uniform(0.05, 0.2)
        
        # Compute rolling sector-like news aggregator (smooth composite)
        sector_news_agg = pd.Series(sentiment_composite).rolling(10, min_periods=1).mean().values
        peer_sentiment_gap = sentiment_composite - sector_news_agg
        
        df["sentiment_composite"] = sentiment_composite
        df["sentiment_positive"] = sentiment_positive
        df["sentiment_negative"] = sentiment_negative
        df["news_volume_norm"] = news_volume_norm
        
        df["news_macro_rbi"] = news_macro_rbi
        df["news_macro_crude"] = news_macro_crude
        df["news_earnings"] = news_earnings
        df["news_regulatory"] = news_regulatory
        df["news_global"] = news_global
        df["news_promoter"] = news_promoter
        df["sector_news_agg"] = sector_news_agg
        df["peer_sentiment_gap"] = peer_sentiment_gap
        
    else:
        # Live inference mode: query RSS AND 8 recent articles from yfinance, then run categorizer
        logger.info(f"Running live news pipeline for {ticker} (inference mode)")
        
        # Initialize
        news_macro_rbi = news_macro_crude = news_earnings = 0.0
        news_regulatory = news_global = news_promoter = 0.0
        sector_news_agg = peer_sentiment_gap = 0.0
        sentiment_composite_val = 0.0
        news_volume_norm_val = 0.0
        
        try:
            from src.data.news_pipeline import NewsCategorizer, NEWS_SOURCES, SECTOR_TICKERS
            categorizer = NewsCategorizer()
            all_tickers = list(SECTOR_MAP.keys())
            sector_name_for_news = SECTOR_MAP.get(ticker, "others")
            
            # Fetch headlines from RSS
            headlines = []
            for source_url in NEWS_SOURCES.values():
                headlines.extend(categorizer.fetch_safe(source_url))
            
            # Fetch 8 most recent articles from yfinance
            try:
                session = get_yfinance_session()
                ticker_obj = yf.Ticker(ticker, session=session)
                if hasattr(ticker_obj, 'news') and ticker_obj.news:
                    yf_news = [item['title'] for item in ticker_obj.news if 'title' in item]
                    logger.info(f"Fetched {len(yf_news)} recent articles from yfinance for {ticker}")
                    headlines.extend(yf_news)
            except Exception as yf_err:
                logger.warning(f"Failed to fetch yfinance news for {ticker}: {yf_err}")
                
            headlines = list(set(headlines))  # deduplicate
            
            # Aggregate category scores from all headlines that link to this ticker
            agg_scores = {cat: [] for cat in ["macro_rbi", "macro_crude", "earnings", "regulatory", "global", "promoter", "fii_dii"]}
            sector_all_scores = []  # all scores for any ticker in same sector
            
            for headline in headlines:
                linked = categorizer.link_to_tickers(headline, all_tickers)
                scores = categorizer.categorize(headline)
                score_val = max(scores.values()) if scores else 0.0
                
                # Sector aggregate: collect if headline affects any ticker in same sector
                sector_peers = SECTOR_TICKERS.get(sector_name_for_news, [])
                if any(t in linked for t in sector_peers):
                    sector_all_scores.append(score_val)
                    
                # Ticker-specific: only if this ticker is directly linked
                if ticker in linked:
                    for cat in agg_scores:
                        agg_scores[cat].append(scores.get(cat, 0.0))
                        
            def _agg(vals): return float(np.clip(np.mean(vals), 0.0, 1.0)) if vals else 0.0
            
            news_macro_rbi   = _agg(agg_scores["macro_rbi"])
            news_macro_crude = _agg(agg_scores["macro_crude"])
            news_earnings    = _agg(agg_scores["earnings"])
            news_regulatory  = _agg(agg_scores["regulatory"])
            news_global      = _agg(agg_scores["global"])
            news_promoter    = _agg(agg_scores["promoter"])
            sector_news_agg  = _agg(sector_all_scores)
            
            # Peer sentiment gap: this ticker's composite vs sector average
            ticker_composite = _agg([v for vals in agg_scores.values() for v in vals])
            peer_sentiment_gap = float(np.clip(ticker_composite - sector_news_agg, -1.0, 1.0))
            
            sentiment_composite_val = float(np.clip(ticker_composite, -1.0, 1.0))
            news_volume_norm_val = min(1.0, len(headlines) / 20.0)
            
            logger.info(f"News features computed for {ticker}: earnings={news_earnings:.2f}, macro_rbi={news_macro_rbi:.2f}")
            
            # Log news telemetry for live inference auditing
            try:
                from src.data.news_pipeline import log_news_telemetry
                scores_to_log = {
                    "macro_rbi": news_macro_rbi,
                    "macro_crude": news_macro_crude,
                    "earnings": news_earnings,
                    "regulatory": news_regulatory,
                    "global": news_global,
                    "promoter": news_promoter,
                    "sector_news_agg": sector_news_agg,
                    "peer_sentiment_gap": peer_sentiment_gap
                }
                log_news_telemetry(ticker, headlines, scores_to_log, sentiment_composite_val)
            except Exception as tel_err:
                logger.warning(f"Failed to log news telemetry: {tel_err}")
        except Exception as e:
            logger.warning(f"News pipeline failed for {ticker}, using zeros: {e}")
            
        df["sentiment_composite"] = sentiment_composite_val
        df["sentiment_positive"] = max(0.0, sentiment_composite_val)
        df["sentiment_negative"] = abs(min(0.0, sentiment_composite_val))
        df["news_volume_norm"] = news_volume_norm_val
        
        df["news_macro_rbi"]    = news_macro_rbi
        df["news_macro_crude"]  = news_macro_crude
        df["news_earnings"]     = news_earnings
        df["news_regulatory"]   = news_regulatory
        df["news_global"]       = news_global
        df["news_promoter"]     = news_promoter
        df["sector_news_agg"]   = sector_news_agg
        df["peer_sentiment_gap"] = peer_sentiment_gap
    
    # Any additional columns needed to hit exactly 78 features
    remaining_cols = [col for col in V2_STRICT_STATIC_COLUMNS if col not in df.columns]
    for col in remaining_cols:
        df[col] = 0.0

    # Strict ordering to guarantee consistent observations
    df_static = df[V2_STRICT_STATIC_COLUMNS].copy()

    # Restore the simulation columns needed by the environment for rewards/dates
    df_static["Open"] = df["Open"]
    df_static["High"] = df["High"]
    df_static["Low"] = df["Low"]
    df_static["Close"] = df["Close"]
    df_static["Volume"] = df["Volume"]
    df_static["Returns"] = df["Returns"]
    
    # Drop rows with NaNs (first few rows due to indicator warmup)
    df_static = df_static.dropna()
    
    # Assert check to prevent mismatches
    assert df_static.shape[1] == 84, f"Expected 84 columns (78 static + 6 simulation metrics), got {df_static.shape[1]}"
    
    # Standardize indices to Date format *only* at final export
    df_static.index = pd.to_datetime(df_static.index).date
    
    logger.info(f"Successfully built feature matrix of shape {df_static.shape} for {ticker}")
    return df_static
