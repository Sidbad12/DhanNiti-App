# scripts/seed_yfinance.py
import sys
import os
from pathlib import Path
from datetime import datetime

# Adjust Python path to import from src
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database.supabase_client import DhanNitiDatabase
from src.data.extractor import get_yfinance_session
import yfinance as yf

def seed_ticker(db, ticker_symbol, period='1y'):
    """Fetch 1Y daily historical candle data for a ticker and save it to Supabase."""
    # Clean ticker for Yahoo Finance format
    yf_ticker = ticker_symbol
    if ":" in yf_ticker:
        yf_ticker = yf_ticker.split(":")[-1]
    if yf_ticker.endswith("-EQ"):
        yf_ticker = yf_ticker.replace("-EQ", "")
    if not yf_ticker.endswith(".NS") and not yf_ticker.startswith("^"):
        if "NIFTY" in yf_ticker.upper():
            yf_ticker = "^NSEI"
        else:
            yf_ticker = f"{yf_ticker}.NS"
            
    print(f"  Fetching {yf_ticker} ({period})...")
    
    try:
        session = get_yfinance_session()
        stock = yf.Ticker(yf_ticker, session=session)
        hist = stock.history(period=period)
        
        if hist.empty:
            print(f"  ✗ No data found for {yf_ticker}")
            return 0
            
        db_rows = []
        for date, row in hist.iterrows():
            date_str = date.strftime("%Y-%m-%d")
            db_rows.append({
                "ticker": yf_ticker,
                "date": date_str,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "source": "yfinance"
            })
            
        if db_rows:
            success = db.upsert_historical_candles(db_rows)
            if success:
                print(f"  ✓ {yf_ticker}: {len(db_rows)} daily candles saved to Supabase.")
                return len(db_rows)
            else:
                print(f"  ✗ Failed to save candles for {yf_ticker} to Supabase.")
    except Exception as e:
        print(f"  ✗ Error seeding {yf_ticker}: {e}")
        
    return 0

def run_seed(tickers=None):
    db = DhanNitiDatabase()
    if not db.client:
        print("Error: Supabase client not initialized. Make sure SUPABASE_URL and SUPABASE_KEY are in your .env")
        return
        
    if not tickers:
        # Default major Indian stocks
        tickers = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN", "LT", "BHARTIARTL"]
        
    print(f"\n[Seeder] Seeding historical daily price candles for {len(tickers)} tickers...")
    total_inserted = 0
    
    for t in tickers:
        total_inserted += seed_ticker(db, t)
        
    print(f"\n[Seeder] Seeding complete. Total rows inserted/updated: {total_inserted}\n")

if __name__ == "__main__":
    cli_tickers = sys.argv[1:] if len(sys.argv) > 1 else None
    run_seed(cli_tickers)
