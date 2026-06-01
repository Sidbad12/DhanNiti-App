"""
DhanNiti — Feature Engineering
pandas_ta technical indicators → feature matrix for XGBoost
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import pandas_ta as ta
except ImportError:
    raise ImportError("pandas_ta required: pip install pandas-ta")

from src.settings import FEATURE_CONFIG

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════════════════

def _safe_merge(base: pd.DataFrame, ta_result: Optional[pd.Series | pd.DataFrame]) -> pd.DataFrame:
    """Merge a TA result into base df without crashing on None."""
    if ta_result is None:
        return base
    if isinstance(ta_result, pd.DataFrame):
        return pd.concat([base, ta_result], axis=1)
    return pd.concat([base, ta_result.rename(ta_result.name)], axis=1)


def _log_return(series: pd.Series, period: int = 1) -> pd.Series:
    return np.log(series / series.shift(period))


def _normalise_by_price(series: pd.Series, price: pd.Series) -> pd.Series:
    """Scale indicator relative to price — removes price-level bias."""
    return (series - price) / price


# ════════════════════════════════════════════════════════════
# INDICATOR GROUPS
# ════════════════════════════════════════════════════════════

def _add_momentum(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """RSI (multiple periods), ROC, Momentum, MACD."""
    close = df["Close"]

    for period in cfg["rsi_periods"]:
        rsi = ta.rsi(close, length=period)
        if rsi is not None:
            df[f"rsi_{period}"] = rsi / 100.0      # normalise to [0, 1]

    roc = ta.roc(close, length=cfg["roc_period"])
    if roc is not None:
        df["roc"] = roc / 100.0

    mom = ta.mom(close, length=cfg["mom_period"])
    if mom is not None:
        df["mom"] = _normalise_by_price(mom + close, close)

    macd_df = ta.macd(
        close,
        fast=cfg["macd_fast"],
        slow=cfg["macd_slow"],
        signal=cfg["macd_signal"],
    )
    if macd_df is not None:
        macd_col    = f"MACD_{cfg['macd_fast']}_{cfg['macd_slow']}_{cfg['macd_signal']}"
        signal_col  = f"MACDs_{cfg['macd_fast']}_{cfg['macd_slow']}_{cfg['macd_signal']}"
        hist_col    = f"MACDh_{cfg['macd_fast']}_{cfg['macd_slow']}_{cfg['macd_signal']}"
        if macd_col in macd_df.columns:
            df["macd_line"]   = _normalise_by_price(macd_df[macd_col] + close, close)
            df["macd_signal"] = _normalise_by_price(macd_df[signal_col] + close, close)
            df["macd_hist"]   = _normalise_by_price(macd_df[hist_col] + close, close)

    return df


def _add_oscillators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """StochRSI, CCI, Williams %R, KST."""
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    stochrsi = ta.stochrsi(close, length=cfg["stochrsi_period"])
    if stochrsi is not None:
        for col in stochrsi.columns:
            df[f"stochrsi_{col.lower()}"] = stochrsi[col] / 100.0

    cci = ta.cci(high, low, close, length=cfg["cci_period"])
    if cci is not None:
        df["cci"] = cci / 200.0     # roughly normalise to [-1, 1]

    willr = ta.willr(high, low, close, length=cfg["willr_period"])
    if willr is not None:
        df["willr"] = willr / 100.0

    if cfg.get("kst_enabled"):
        kst = ta.kst(close)
        if kst is not None:
            df = _safe_merge(df, kst)

    return df


def _add_trend(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """SMA, EMA crossovers, VWMA — all price-normalised."""
    close  = df["Close"]
    volume = df["Volume"]

    for p in cfg["sma_periods"]:
        sma = ta.sma(close, length=p)
        if sma is not None:
            df[f"sma_{p}_dist"] = _normalise_by_price(sma, close)

    for p in cfg["ema_periods"]:
        ema = ta.ema(close, length=p)
        if ema is not None:
            df[f"ema_{p}_dist"] = _normalise_by_price(ema, close)

    # EMA crossover signals (fast - slow, normalised)
    ema_pairs = [(5, 20), (10, 50)]
    for fast, slow in ema_pairs:
        ema_f = ta.ema(close, length=fast)
        ema_s = ta.ema(close, length=slow)
        if ema_f is not None and ema_s is not None:
            df[f"ema_cross_{fast}_{slow}"] = (ema_f - ema_s) / close

    vwma = ta.vwma(close, volume, length=cfg["vwma_period"])
    if vwma is not None:
        df["vwma_dist"] = _normalise_by_price(vwma, close)

    # Log returns at multiple horizons
    for h in [1, 3, 5, 10]:
        df[f"log_ret_{h}d"] = _log_return(close, h)

    return df


def _add_volatility(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Bollinger Bands, ATR, Keltner Channel."""
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    bb = ta.bbands(close, length=cfg["bbands_period"], std=cfg["bbands_std"])
    if bb is not None:
        upper_col = f"BBU_{cfg['bbands_period']}_{float(cfg['bbands_std'])}"
        lower_col = f"BBL_{cfg['bbands_period']}_{float(cfg['bbands_std'])}"
        mid_col   = f"BBM_{cfg['bbands_period']}_{float(cfg['bbands_std'])}"
        bw_col    = f"BBB_{cfg['bbands_period']}_{float(cfg['bbands_std'])}"
        if upper_col in bb.columns:
            df["bb_upper_dist"] = _normalise_by_price(bb[upper_col], close)
            df["bb_lower_dist"] = _normalise_by_price(bb[lower_col], close)
            df["bb_mid_dist"]   = _normalise_by_price(bb[mid_col],   close)
            df["bb_width"]      = (bb[upper_col] - bb[lower_col]) / bb[mid_col]

    atr = ta.atr(high, low, close, length=cfg["atr_period"])
    if atr is not None:
        df["atr_norm"] = atr / close    # ATR as % of price

    kc = ta.kc(high, low, close, length=cfg["kc_period"])
    if kc is not None:
        kcu_col = f"KCUe_{cfg['kc_period']}_2"
        kcl_col = f"KCLe_{cfg['kc_period']}_2"
        if kcu_col in kc.columns:
            df["kc_upper_dist"] = _normalise_by_price(kc[kcu_col], close)
            df["kc_lower_dist"] = _normalise_by_price(kc[kcl_col], close)

    # Rolling volatility (realised)
    for window in [5, 10, 20]:
        df[f"realised_vol_{window}d"] = (
            _log_return(close).rolling(window).std() * np.sqrt(252)
        )

    return df


def _add_volume(df: pd.DataFrame) -> pd.DataFrame:
    """OBV, A/D, EFI, NVI, PVI — volume-based signals."""
    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    obv = ta.obv(close, volume)
    if obv is not None:
        # OBV rate of change (more useful than raw OBV)
        df["obv_roc"] = obv.pct_change(5)

    ad = ta.ad(high, low, close, volume)
    if ad is not None:
        df["ad_roc"] = ad.pct_change(5)

    efi = ta.efi(close, volume)
    if efi is not None:
        df["efi"] = np.sign(efi) * np.log1p(np.abs(efi))  # signed log scale

    # Volume ratio: today vs 20d average
    vol_ma = volume.rolling(20).mean()
    df["volume_ratio"] = volume / (vol_ma + 1e-9)

    return df


def _add_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Market regime proxy features.
    - 50d/200d ratio (trend regime)
    - ATR percentile (volatility regime)
    - RSI14 regime zone (overbought/oversold/neutral)
    """
    close = df["Close"]

    sma50  = ta.sma(close, length=50)
    sma200 = ta.sma(close, length=200)
    if sma50 is not None and sma200 is not None:
        df["trend_regime"] = (sma50 / (sma200 + 1e-9)) - 1.0

    atr = ta.atr(df["High"], df["Low"], close, length=14)
    if atr is not None:
        atr_norm = atr / close
        df["vol_regime"] = atr_norm.rank(pct=True)     # percentile rank

    rsi14 = ta.rsi(close, length=14)
    if rsi14 is not None:
        df["rsi_zone"] = pd.cut(
            rsi14,
            bins=[0, 30, 50, 70, 100],
            labels=[0, 1, 2, 3],           # oversold/neutral-low/neutral-high/overbought
        ).astype(float)

    return df


# ════════════════════════════════════════════════════════════
# LABEL GENERATION
# ════════════════════════════════════════════════════════════

def generate_label(
    data: pd.DataFrame,
    lookahead: int = 5,
    thresh: float = 0.01,
    col: str = "Close",
) -> pd.Series:
    """
    3-class label based on mean of next `lookahead` closes.
      2 = Bullish  (future_mean ≥ current × (1 + thresh))
      1 = Bearish  (future_mean ≤ current × (1 - thresh))
      0 = Neutral
    """
    future_mean = (
        data[col]
        .shift(-lookahead)
        .rolling(window=lookahead, min_periods=lookahead)
        .mean()
    )
    pct = (future_mean - data[col]) / (data[col] + 1e-9)
    labels = np.select(
        [pct >= thresh, pct <= -thresh],
        [2, 1],
        default=0,
    )
    return pd.Series(labels, index=data.index, name=f"label_la{lookahead}_th{thresh:.3f}")


def add_all_labels(df: pd.DataFrame, lookaheads: list, thresholds: list) -> pd.DataFrame:
    """Add all label combinations to df."""
    from src.settings import LABEL_LOOKAHEADS, LABEL_THRESHOLDS
    la_list = lookaheads or LABEL_LOOKAHEADS
    th_list = thresholds or LABEL_THRESHOLDS
    for la in la_list:
        for th in th_list:
            df[f"label_la{la}_th{th:.3f}"] = generate_label(df, lookahead=la, thresh=th)
    return df


# ════════════════════════════════════════════════════════════
# MAIN PUBLIC API
# ════════════════════════════════════════════════════════════

def build_features(
    raw_df: pd.DataFrame,
    cfg: dict | None = None,
    add_labels: bool = True,
    lookaheads: list | None = None,
    thresholds: list | None = None,
) -> pd.DataFrame:
    """
    Full feature engineering pipeline for one ticker.

    Args:
        raw_df    : DataFrame with columns [Open, High, Low, Close, Volume]
                    and a DatetimeIndex.
        cfg       : Feature config dict. Defaults to settings.FEATURE_CONFIG.
        add_labels: Whether to append classification labels.
        lookaheads: Label lookahead windows. Defaults to settings.LABEL_LOOKAHEADS.
        thresholds: Label return thresholds. Defaults to settings.LABEL_THRESHOLDS.

    Returns:
        Feature-enriched DataFrame. NaN rows from indicator warmup are retained
        (caller should dropna() before training).
    """
    cfg = cfg or FEATURE_CONFIG

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing  = required - set(raw_df.columns)
    if missing:
        raise ValueError(f"raw_df missing columns: {missing}")

    df = raw_df.copy()

    logger.debug("Building momentum features...")
    df = _add_momentum(df, cfg)

    logger.debug("Building oscillator features...")
    df = _add_oscillators(df, cfg)

    logger.debug("Building trend features...")
    df = _add_trend(df, cfg)

    logger.debug("Building volatility features...")
    df = _add_volatility(df, cfg)

    logger.debug("Building volume features...")
    df = _add_volume(df)

    logger.debug("Building regime features...")
    df = _add_regime_features(df)

    if add_labels:
        from src.settings import LABEL_LOOKAHEADS, LABEL_THRESHOLDS
        df = add_all_labels(
            df,
            lookaheads=lookaheads or LABEL_LOOKAHEADS,
            thresholds=thresholds or LABEL_THRESHOLDS,
        )

    n_features = len([c for c in df.columns if not c.startswith("label_")
                      and c not in {"Open", "High", "Low", "Close", "Volume"}])
    logger.info(f"Feature matrix built: {len(df)} rows × {n_features} features")

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return feature column names (excludes OHLCV and label columns)."""
    exclude = {"Open", "High", "Low", "Close", "Volume", "Adj Close"}
    return [
        c for c in df.columns
        if c not in exclude and not c.startswith("label_")
    ]


def build_features_for_portfolio(
    portfolio_data: dict[str, pd.DataFrame],
    cfg: dict | None = None,
    add_labels: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Run build_features() for each ticker in the portfolio.

    Args:
        portfolio_data: {ticker: DataFrame with OHLCV}
        cfg           : Feature config. Defaults to settings.FEATURE_CONFIG.
        add_labels    : Whether to append labels.

    Returns:
        {ticker: feature_df}
    """
    result: dict[str, pd.DataFrame] = {}
    for ticker, df in portfolio_data.items():
        try:
            result[ticker] = build_features(df, cfg=cfg, add_labels=add_labels)
            logger.info(f"{ticker}: {result[ticker].shape[1]} columns built")
        except Exception as e:
            logger.error(f"{ticker}: feature build failed — {e}")
    return result