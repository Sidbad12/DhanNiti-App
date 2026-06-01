# Fyers DataFeed implementation for DhanNiti

from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws
from .auth import FyersAuth
from .processor import process_hist_data, process_live_data
import datetime
import time
import random
import polars as pl

def generate_mock_5s_candles(symbol: str, days_back: int = 1) -> list:
    """Generates realistic 5-second candles for backfilling/testing."""
    now = int(time.time())
    interval = 5
    # 4500 candles per day approx (6.25 hours * 720 candles/hour = 4500)
    num_candles = 4500 * days_back
    
    base_price = 25000.0
    if "BANKNIFTY" in symbol:
        base_price = 50000.0
    elif "NIFTY" in symbol:
        base_price = 25000.0
    elif "RELIANCE" in symbol:
        base_price = 2800.0
    elif "SBIN" in symbol:
        base_price = 800.0
    
    price = base_price
    candles = []
    start_ts = now - (num_candles * interval)
    
    for i in range(num_candles):
        ts = start_ts + i * interval
        op = price
        noise = random.normalvariate(0, 1.5 if base_price > 10000 else 0.4)
        cl = price + noise
        hi = max(op, cl) + random.uniform(0, 0.8 if base_price > 10000 else 0.15)
        lo = min(op, cl) - random.uniform(0, 0.8 if base_price > 10000 else 0.15)
        vol = random.randint(100, 4000)
        
        candles.append([ts, op, hi, lo, cl, vol])
        price = cl
        
    return candles


class FyersDataFeed:
    """Optimized Fyers historical data feed handler."""
    
    def __init__(self, force_refresh_auth=False):
        self.client_id, self.access_token = FyersAuth.get_fyers_credentials()
        self._hist_model = None

    @property
    def hist_model(self):
        """Lazy initialization of historical data model with fresh token."""
        if self._hist_model is None or not self.access_token:
            self.client_id, self.access_token = FyersAuth.get_fyers_credentials()
            self._hist_model = fyersModel.FyersModel(
                client_id=self.client_id, 
                is_async=False, 
                token=self.access_token, 
                log_path=""
            )
        return self._hist_model

    def get_historical_data(self, symbol, resolution=None, start_date=None, end_date=None, 
                          date_format=None, timeframe='5min', process=True, time_now=True, 
                          days_back=29, data_frame=False, bucket_size=0.05, multiplier=100, footprint=True):
        """
        Historical data fetcher with default 29-day lookback.
        Fetches 5S resolution candles and resamples them into target timeframes with footprint.
        """
        if time_now:
            now = datetime.datetime.now()
            end_date = int(time.mktime(now.timetuple()))
            start_date = int(time.mktime((now - datetime.timedelta(days=days_back)).timetuple()))
            date_format = '0'
            used_resolution = '5S'
        else:
            if not resolution:
                raise ValueError("resolution must be provided if time_now is False")
            used_resolution = resolution

        def fetch_and_process(sym):
            import os
            is_mock = os.environ.get("MOCK_DATA") == "true" or not self.access_token
            
            if is_mock:
                print(f"[MOCK DATA FEED]: Generating mock 5S candles for {sym}")
                candles = generate_mock_5s_candles(sym, days_back=days_back)
            else:
                try:
                    data = {
                        "symbol": sym,
                        "resolution": used_resolution,
                        "date_format": str(date_format),
                        "range_from": str(start_date),
                        "range_to": str(end_date),
                        "cont_flag": "1"
                    }
                    raw = self.hist_model.history(data)
                    if not raw or raw.get('s') != 'ok':
                        raise Exception(f"Fyers historical fetch failed: {raw}")
                    candles = raw.get('candles', [])
                except Exception as e:
                    print(f"[HISTORICAL FETCH FAILED]: {e}. Falling back to mock data.")
                    candles = generate_mock_5s_candles(sym, days_back=days_back)
            
            df = pl.DataFrame(
                candles, 
                schema=["timestamp", "open", "high", "low", "close", "volume"], 
                orient="row"
            )
            
            if process:
                return process_hist_data(
                    df=df, timeframe=timeframe, data_frame=data_frame, 
                    bucket_size=bucket_size, multiplier=multiplier, footprint=footprint
                )
            return df

        if isinstance(symbol, list):
            return {sym: fetch_and_process(sym) for sym in symbol}
        else:
            return fetch_and_process(symbol)
        
    def get_live_update(self, symbol, timeframe='5m', bucket_size=0.05, multiplier=100):
        """Subscribe to live data updates (Fyers socket-level legacy callback)."""
        data_type = "SymbolUpdate"

        def onmessage(message):
            processed = process_live_data(
                message, timeframe=timeframe, bucket_size=bucket_size, multiplier=multiplier
            )
            print(processed)

        def onerror(message):
            print("Error:", message)

        def onclose(message):
            print("Connection closed:", message)

        def onopen():
            live_data.subscribe(symbols=[symbol], data_type=data_type)
            live_data.keep_running()

        live_data = data_ws.FyersDataSocket(
            access_token=self.access_token,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=onopen,
            on_close=onclose,
            on_error=onerror,
            on_message=onmessage,            
        )
        live_data.connect()
        return live_data
