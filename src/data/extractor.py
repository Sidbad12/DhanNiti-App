"""
Data extraction module for fetching stock data and Alternative Market Data.
Supports OHLCV via yfinance and custom scrapers for FII/DII, PCR, and VIX.
"""

from __future__ import annotations

import os
import pickle
import logging
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

from src.settings import END_DATE, START_DATE, ALTERNATIVE_DATA_CONFIG

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# CORE PRICE DATA (yfinance)
# ════════════════════════════════════════════════════════════

def _process_ticker_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process raw ticker DataFrame: keep OHLCV, extract Price (Close), calculate Returns, normalise dates.
    """
    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    for col in required_cols:
        if col not in df.columns:
            if col in ["Open", "High", "Low"] and "Close" in df.columns:
                df[col] = df["Close"]
            else:
                df[col] = 0.0

    df = df[required_cols].copy()
    df["Price"] = df["Close"]
    df["Returns"] = df["Close"].pct_change()
    df = df.dropna()

    # Convert index to date type
    df.index = pd.to_datetime(df.index).date
    df.index.name = "Date"

    return df


def get_yfinance_session() -> requests.Session:
    """Create a requests session with proper headers to bypass Yahoo Finance blocks."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def _extract_single_ticker_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Extract and process data for a single ticker with Supabase caching."""
    try:
        # 1. Try to load from Supabase first
        from src.database.supabase_client import DhanNitiDatabase
        db = DhanNitiDatabase()
        db_candles = db.get_historical_candles(ticker, start_date, end_date)
        
        # Calculate expected trading days (roughly 5/7 of calendar days)
        try:
            cal_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
            expected_trading_days = int(cal_days * 5 / 7)
        except Exception:
            expected_trading_days = 200 # sensible default
            
        if db_candles and len(db_candles) >= max(10, expected_trading_days - 15):
            logger.info(f"Loaded {len(db_candles)} candles for {ticker} from Supabase for pipeline.")
            rows = []
            for r in db_candles:
                rows.append({
                    "Date": pd.to_datetime(r["date"]),
                    "Open": float(r["open"]),
                    "High": float(r["high"]),
                    "Low": float(r["low"]),
                    "Close": float(r["close"]),
                    "Volume": float(r["volume"]),
                })
            df = pd.DataFrame(rows).set_index("Date").sort_index()
            df_processed = _process_ticker_dataframe(df)
            return df_processed

        # 2. Fetch from yfinance
        session = get_yfinance_session()
        stock = yf.Ticker(ticker, session=session)
        df = stock.history(start=start_date, end=end_date)
        if df.empty:
            logger.warning(f"No data available for ticker: {ticker}")
            # Fallback to DB if we have any data
            if db_candles:
                rows = []
                for r in db_candles:
                    rows.append({
                        "Date": pd.to_datetime(r["date"]),
                        "Open": float(r["open"]),
                        "High": float(r["high"]),
                        "Low": float(r["low"]),
                        "Close": float(r["close"]),
                        "Volume": float(r["volume"]),
                    })
                df = pd.DataFrame(rows).set_index("Date").sort_index()
                return _process_ticker_dataframe(df)
            return None

        df_processed = _process_ticker_dataframe(df)
        
        # 3. Save to Supabase for future requests
        db_rows = []
        for date, row in df.iterrows():
            db_rows.append({
                "ticker": ticker,
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        if db_rows:
            db.upsert_historical_candles(db_rows)
            logger.info(f"Saved {len(db_rows)} downloaded candles for {ticker} to Supabase.")

        return df_processed

    except Exception as e:
        logger.error(f"Error downloading {ticker}: {e}")
        return None


def extract_data(
    tickers: list[str],
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> dict[str, pd.DataFrame]:
    """Extract historical stock data for multiple tickers, with local file caching."""
    cache_dir = "data/cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    # Create clean cache key
    clean_tickers = "_".join(sorted([t.replace("^", "").replace(".NS", "") for t in tickers]))
    cache_key = f"raw_data_{clean_tickers}_{start_date}_{end_date}.pkl"
    cache_path = os.path.join(cache_dir, cache_key)
    
    # Check if cache is fresh (modified less than 12 hours ago)
    if os.path.exists(cache_path):
        try:
            mtime = os.path.getmtime(cache_path)
            if (datetime.now().timestamp() - mtime) < 12 * 3600:
                with open(cache_path, "rb") as f:
                    cached_data = pickle.load(f)
                logger.info(f"Loaded raw data for {len(cached_data)} tickers from local cache: {cache_path}")
                return cached_data
        except Exception as e:
            logger.warning(f"Failed to load raw cache {cache_path}: {e}")

    # Fallback to downloading
    all_stock_data: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        df_processed = _extract_single_ticker_data(ticker, start_date, end_date)
        if df_processed is not None and not df_processed.empty:
            all_stock_data[ticker] = df_processed

    # Save to cache if we successfully retrieved data
    if all_stock_data:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(all_stock_data, f)
            logger.info(f"Saved downloaded stock data to local cache: {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to save raw cache {cache_path}: {e}")

    return all_stock_data


# ════════════════════════════════════════════════════════════
# ALTERNATIVE DATA EXTRACTION (Phase 2)
# ════════════════════════════════════════════════════════════

def _get_nse_session() -> requests.Session:
    """
    Create a requests session with proper headers to bypass basic NSE blocks.
    Hits the main page first to acquire required cookies.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    })
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception as e:
        logger.debug(f"Failed to prime NSE session cookies: {e}")
    return session


def fetch_fii_dii_data() -> dict[str, float]:
    """
    Scrape NSE's daily FII/DII net buy/sell figures.
    Returns: {"fii_net": float, "dii_net": float} (values in Crores INR)
    """
    if not ALTERNATIVE_DATA_CONFIG.get("fetch_fii_dii", True):
        return {"fii_net": 0.0, "dii_net": 0.0}

    session = _get_nse_session()
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    
    try:
        res = session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            fii_net = 0.0
            dii_net = 0.0
            # Parse list of dicts. Example element: {"category": "FII/FPI", "netValue": "-1200.50"}
            for item in data:
                cat = item.get("category", "")
                val = str(item.get("netValue", "0")).replace(",", "")
                try:
                    val_float = float(val)
                except ValueError:
                    val_float = 0.0
                    
                if "FII" in cat:
                    fii_net = val_float
                elif "DII" in cat:
                    dii_net = val_float
                    
            logger.info(f"Fetched FII/DII Net Flow: FII={fii_net} Cr, DII={dii_net} Cr")
            return {"fii_net": fii_net, "dii_net": dii_net}
        else:
            logger.warning(f"NSE FII/DII API returned status {res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching FII/DII data: {e}")
        
    return {"fii_net": 0.0, "dii_net": 0.0}


def fetch_options_pcr() -> float:
    """
    Fetch Nifty Put-Call Ratio (PCR) from NSE options chain data.
    """
    if not ALTERNATIVE_DATA_CONFIG.get("fetch_pcr", True):
        return 1.0

    session = _get_nse_session()
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    
    try:
        res = session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            records = data.get("records", {})
            total_ce_oi = records.get("totalCE", {}).get("totOI", 1)
            total_pe_oi = records.get("totalPE", {}).get("totOI", 1)
            
            if total_ce_oi == 0:
                total_ce_oi = 1 # Prevent ZeroDivisionError
                
            pcr = total_pe_oi / total_ce_oi
            pcr = round(pcr, 3)
            logger.info(f"Fetched Nifty PCR: {pcr}")
            return pcr
        else:
            logger.warning(f"NSE Option Chain API returned status {res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching PCR data: {e}")
        
    return 1.0 # Neutral fallback


def fetch_nifty_vix() -> float:
    """
    Fetch current India VIX via yfinance.
    """
    if not ALTERNATIVE_DATA_CONFIG.get("fetch_vix", True):
        return 15.0

    try:
        session = get_yfinance_session()
        vix_ticker = yf.Ticker("^INDIAVIX", session=session)
        hist = vix_ticker.history(period="5d")
        if not hist.empty:
            vix = round(float(hist["Close"].iloc[-1]), 2)
            logger.info(f"Fetched India VIX: {vix}")
            return vix
    except Exception as e:
        logger.error(f"Error fetching India VIX: {e}")
        
    return 15.0 # Neutral historical average fallback
