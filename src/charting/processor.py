"""Live tick and historical processing helpers for DhanNiti Charting.

This module provides:
- CandleAggregator: per-timeframe live tick to candle aggregator with footprint.
- TickToBucket5s: simple 5-second tick aggregator producing OHLCV buckets.
- process_hist_data: polars-based historical resampling with footprint building.
- process_live_data: backwards-compatible entry point used by the app.
- clear_processor_state: utility to clear in-memory aggregator state.

The implementation provides live tick aggregation and historical resampling
with proper cumulative delta calculation that resets at market open each day.
"""

import math
import logging
from typing import Any
import polars as pl
from collections import deque, defaultdict
from fractions import Fraction
from decimal import Decimal, ROUND_FLOOR, InvalidOperation, getcontext
from typing import Dict, List, Tuple, Optional, Union, Iterable
from datetime import datetime, time, date

# Keep a small in-memory state to mirror previous behaviour
_candle_state: Dict[str, 'CandleAggregator'] = {}

logger = logging.getLogger(__name__)

# Shared interval map
_INTERVAL_MAP = {'1m': 60, '5m': 300, '15m': 900, '1d': 86400}

# Timestamp magnitude thresholds (for normalize_timestamp_to_seconds)
NS_THRESHOLD = 1e18
US_THRESHOLD = 1e15
MS_THRESHOLD = 1e12

# Market hours configuration (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Decimal precision for historical operations
getcontext().prec = 16

# ----------------- Module-level helpers (shared) -----------------

def normalize_timestamp_to_seconds(raw_ts) -> Optional[int]:
    """Normalize timestamps in various units to integer seconds.
    Returns None for invalid inputs.
    """
    # Accept datetime objects directly
    if isinstance(raw_ts, datetime):
        return int(raw_ts.timestamp())

    # Accept ISO-8601 strings
    if isinstance(raw_ts, str):
        try:
            # Try parse common ISO format
            dt = datetime.fromisoformat(raw_ts)
            return int(dt.timestamp())
        except Exception:
            pass

    try:
        t = float(raw_ts)
    except (ValueError, TypeError):
        return None

    if t <= 0:
        return None

    # heuristics: >=NS_THRESHOLD -> ns, >=US_THRESHOLD -> us, >=MS_THRESHOLD -> ms
    if t >= NS_THRESHOLD:
        return int(t / 1e9)
    if t >= US_THRESHOLD:
        return int(t / 1e6)
    if t >= MS_THRESHOLD:
        return int(t / 1e3)
    return int(t)

def calculate_aligned_time_bin(timestamp: int, interval_seconds: int) -> int:
    """Align timestamp to market open-based bins (India default 09:15 IST).
    If pytz is available, the function will try to respect timezone-aware
    timestamps; otherwise it falls back to naive datetime.
    """
    # Prefer zoneinfo (stdlib) then fall back to pytz if available.
    tz = None
    try:
        from zoneinfo import ZoneInfo  # type: ignore
        tz = ZoneInfo('Asia/Kolkata')
    except Exception:
        try:
            import pytz
            tz = pytz.timezone('Asia/Kolkata')
        except Exception:
            tz = None

    if tz is not None:
        # Make tz-aware datetime for timestamp and market open using the
        # proper localization API for the tz implementation.
        try:
            dt = datetime.fromtimestamp(timestamp, tz=tz)
        except Exception:
            # fallback to naive
            dt = datetime.fromtimestamp(timestamp)

        market_open_time = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0)
        market_open_naive = datetime.combine(dt.date(), market_open_time)

        # zoneinfo: attach tz by replace; pytz: use localize
        if hasattr(tz, 'localize'):
            try:
                market_open_dt = tz.localize(market_open_naive)
            except Exception:
                market_open_dt = market_open_naive.replace(tzinfo=dt.tzinfo if hasattr(dt, 'tzinfo') else None)
        else:
            market_open_dt = market_open_naive.replace(tzinfo=tz)

        market_open_ts = int(market_open_dt.timestamp())
    else:
        dt = datetime.fromtimestamp(timestamp)
        market_open_time = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0)
        market_open_dt = datetime.combine(dt.date(), market_open_time)
        market_open_ts = int(market_open_dt.timestamp())

    if timestamp < market_open_ts:
        return (timestamp // interval_seconds) * interval_seconds

    seconds_since_open = timestamp - market_open_ts
    candle_period = seconds_since_open // interval_seconds

    return market_open_ts + (candle_period * interval_seconds)

def get_market_open_timestamp(dt: datetime) -> int:
    """Get the market open timestamp for a given datetime."""
    market_open = datetime.combine(dt.date(), time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0))
    # Prefer zoneinfo then pytz; create tz-aware market open if possible
    try:
        from zoneinfo import ZoneInfo  # type: ignore
        ist = ZoneInfo('Asia/Kolkata')
        market_open = market_open.replace(tzinfo=ist)
    except Exception:
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            market_open = ist.localize(market_open)
        except Exception:
            # leave naive
            pass

    return int(market_open.timestamp())

def is_same_trading_day(ts1: int, ts2: int) -> bool:
    """Check if two timestamps belong to the same trading day."""
    dt1 = datetime.fromtimestamp(ts1)
    dt2 = datetime.fromtimestamp(ts2)

    market_open1 = get_market_open_timestamp(dt1)
    market_open2 = get_market_open_timestamp(dt2)

    return market_open1 == market_open2

def get_bucket_key(price: float, bucket_size: float, multiplier: int, use_decimal: bool = True) -> float:
    """Return the price bucket (quantized) for a given price.
    Uses single, consistent floor-based calculation to ensure consistency across
    live and historical processing.
    """
    try:
        price_val = float(price)
        bucket_value = float(bucket_size * multiplier)
        
        # Guard against invalid inputs
        if bucket_value <= 0:
            return round(price_val, 2)
        
        # Single, deterministic floor operation
        bucket_idx = math.floor(price_val / bucket_value)
        bucket_price = bucket_idx * bucket_value
        
        # Single rounding operation to 2 decimals
        return round(bucket_price, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return round(float(price), 2)

def _get_fp_entry_with_tolerance(level: float, fp_map: Dict[float, Dict[str, int]], tolerance: float = 1e-6) -> Dict[str, int]:
    """Get footprint entry with float tolerance to avoid silent mismatches.
    
    Since footprint keys are floats, direct dict lookups can fail due to
    floating-point precision issues. This helper searches with a tolerance.
    """
    for key, value in fp_map.items():
        if abs(key - level) < tolerance:
            return value
    # Not found, return zero entry
    return {'buy': 0, 'sell': 0}

# ----------------- precise integer allocation helpers -----------------

def _proportional_alloc(total: int, weights: Iterable[int]) -> List[int]:
    """Allocate `total` as integers proportional to `weights` using the largest-remainder method
    implemented with exact rational arithmetic to avoid floating point drift.

    Returns a list of ints the same length as weights that sum to total.
    If all weights are zero or total <= 0, falls back to an even split (or zeros).
    """
    w_list = [0 if w is None else int(w) for w in weights]
    n = len(w_list)

    if n == 0:
        return []

    if total <= 0:
        return [0] * n

    s = sum(w_list)

    # When no meaningful weights, distribute evenly (deterministic)
    if s <= 0:
        base = total // n
        res = [base] * n
        rem = total - base * n
        for i in range(rem):
            res[i] += 1
        return res

    # Use Fraction for exact proportional shares
    exact = [Fraction(total * w, s) for w in w_list]
    floored = [int(frac.numerator // frac.denominator) for frac in exact]
    res = floored[:]
    rem = total - sum(res)

    if rem > 0:
        # Compute remainders as Fractions and select largest fractional parts
        remainders = [(i, exact[i] - Fraction(floored[i])) for i in range(n)]
        # sort by fractional remainder descending, tie-break by index for determinism
        remainders.sort(key=lambda x: (x[1], -x[0]), reverse=True)
        for i in range(rem):
            idx = remainders[i][0]
            res[idx] += 1

    return res

def _proportional_alloc_signed(delta: int, weights: Iterable[int]) -> List[int]:
    """Distribute a possibly negative integer `delta` proportionally across weights.
    Uses _proportional_alloc on abs(delta) and restores sign.
    """
    weights_list = list(weights)
    if delta == 0:
        return [0] * len(weights_list)

    sign = 1 if delta > 0 else -1
    alloc = _proportional_alloc(abs(int(delta)), weights_list)
    return [sign * a for a in alloc]


def calculate_aggressor_volumes(msg: dict, vol: int) -> Tuple[int, int]:
    """Determine buy/sell split for a trade volume using the same heuristics
    previously embedded in CandleAggregator._calculate_buy_sell_volume.

    This helper is module-level to allow reuse by other aggregators and
    to make testing straightforward.
    """
    if vol <= 0:
        return 0, 0

    ltp = msg.get('ltp')
    bid = msg.get('bid_price')
    ask = msg.get('ask_price')
    tot_buy_qty = msg.get('tot_buy_qty')
    tot_sell_qty = msg.get('tot_sell_qty')

    eps = 1e-6
    buy = sell = 0

    # Method 1: Use bid/ask spread analysis
    if bid is not None and ask is not None and ltp is not None:
        try:
            bid, ask, ltp = float(bid), float(ask), float(ltp)
            if ask >= bid:  # Valid spread
                if ltp >= ask - eps:
                    buy = vol  # Trade at or above ask = aggressive buy
                elif ltp <= bid + eps:
                    sell = vol  # Trade at or below bid = aggressive sell
                else:
                    # Trade inside spread - use order book pressure
                    if isinstance(tot_buy_qty, (int, float)) and isinstance(tot_sell_qty, (int, float)):
                        total_pressure = tot_buy_qty + tot_sell_qty
                        if total_pressure > 0:
                            buy = int(round(vol * (tot_buy_qty / total_pressure)))
                            sell = vol - buy
                        else:
                            buy = vol // 2
                            sell = vol - buy
                    else:
                        buy = vol // 2
                        sell = vol - buy
            else:
                # Invalid spread - use order book pressure
                if isinstance(tot_buy_qty, (int, float)) and isinstance(tot_sell_qty, (int, float)):
                    total_pressure = tot_buy_qty + tot_sell_qty
                    if total_pressure > 0:
                        buy = int(round(vol * (tot_buy_qty / total_pressure)))
                        sell = vol - buy
                    else:
                        buy = vol // 2
                        sell = vol - buy
                else:
                    buy = vol // 2
                    sell = vol - buy
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # Method 2: Use order book pressure if method 1 didn't work
    if buy + sell == 0:
        if isinstance(tot_buy_qty, (int, float)) and isinstance(tot_sell_qty, (int, float)):
            total_pressure = tot_buy_qty + tot_sell_qty
            if total_pressure > 0:
                try:
                    buy = int(round(vol * (tot_buy_qty / total_pressure)))
                    sell = vol - buy
                except ZeroDivisionError:
                    buy = vol // 2
                    sell = vol - buy

    # Method 3: Use price change as fallback
    if buy + sell == 0:
        ch = msg.get('ch')  # Price change
        if isinstance(ch, (int, float)):
            if ch > 0:
                buy = vol  # Price up = buying pressure
            elif ch < 0:
                sell = vol  # Price down = selling pressure
            else:
                buy = vol // 2
                sell = vol - buy
        else:
            buy = vol // 2
            sell = vol - buy

    # Final reconciliation
    if buy + sell != vol:
        rem = vol - (buy + sell)
        if rem != 0:
            if buy >= sell:
                buy += rem
            else:
                sell += rem

    return max(0, int(buy)), max(0, int(sell))

# ----------------- CandleAggregator (live per-tick) -----------------

class CandleAggregator:
    def __init__(self, timeframe: str, bucket_size: float, multiplier: int):
        self.timeframe = timeframe
        self.bucket_size = float(bucket_size)
        self.multiplier = int(multiplier)

        self._candles: Dict[str, Dict] = {}
        self._footprints: Dict[str, Dict[float, Dict[str, int]]] = {}
        self._recent_trades: Dict[str, deque] = {}
        self._last_ltp: Dict[str, float] = {}
        self._last_cum_volume: Dict[str, int] = {}
        self._last_processed_cum_volume: Dict[str, int] = {}

        # Cumulative delta tracking per symbol (resets each trading day)
        self._session_cum_delta: Dict[str, int] = {}
        self._last_trading_day_per_symbol: Dict[str, int] = {}
        self._current_candle_time: Dict[str, int] = {}

    def process_tick(self, msg: dict) -> Optional[Dict]:
        symbol = msg.get('symbol')
        ltp = msg.get('ltp')
        ts = msg.get('exch_feed_time') or msg.get('last_traded_time')

        if not symbol or ltp is None or ts is None:
            return None

        ts = normalize_timestamp_to_seconds(ts)
        if ts is None:
            return None

        try:
            ltp = float(ltp)
        except (ValueError, TypeError):
            return None

        seconds = _INTERVAL_MAP.get(self.timeframe, 300)
        time_bin = calculate_aligned_time_bin(ts, seconds)

        vol = self._determine_trade_volume(symbol, msg)
        if vol <= 0 or vol > 5_000_000:
            return None

        # Initialize trade tracking for symbol
        if symbol not in self._recent_trades:
            self._recent_trades[symbol] = deque(maxlen=200)

        self._last_ltp[symbol] = ltp

        # Determine buy/sell split for this trade before any reconciliation
        try:
            buy, sell = calculate_aggressor_volumes(msg, vol)
        except Exception:
            logger.exception("Error calculating aggressor volumes for %s", symbol)
            buy, sell = 0, 0

        # Ensure volumes sum correctly
        if buy + sell != vol:
            diff = vol - (buy + sell)
            if buy >= sell:
                buy += diff
            else:
                sell += diff

        # Create robust de-duplication key that includes timestamp, prices and volumes
        trade_key = (ts, round(ltp, 6), int(vol), int(buy), int(sell), msg.get('trade_id'))
        if trade_key in self._recent_trades[symbol]:
            return None
        self._recent_trades[symbol].append(trade_key)

        bucket = get_bucket_key(ltp, self.bucket_size, self.multiplier)

        c = self._candles.get(symbol)
        is_new = (c is None or c.get('time') != time_bin)

        if is_new:
            # Check if this is a new trading day and reset cumulative delta if needed
            current_trading_day = get_market_open_timestamp(datetime.fromtimestamp(time_bin))
            last_trading_day = self._last_trading_day_per_symbol.get(symbol)

            if last_trading_day is None or current_trading_day != last_trading_day:
                # Reset cumulative delta for new trading day
                self._session_cum_delta[symbol] = 0
                self._last_trading_day_per_symbol[symbol] = current_trading_day

            # Track current candle time
            self._current_candle_time[symbol] = time_bin

            # determine opening price: prefer provided daily open for first candle of day, else use ltp
            daily_open = msg.get('open_price')
            candle_open = daily_open if (daily_open is not None and self._is_first_candle_of_day(time_bin)) else ltp

            candle_delta = buy - sell

            # For a new candle, update session cumulative delta
            current_session_cum_delta = self._session_cum_delta.get(symbol, 0) + candle_delta
            self._session_cum_delta[symbol] = current_session_cum_delta

            self._candles[symbol] = {
                'symbol': symbol,
                'time': time_bin,
                'open': candle_open,
                'high': ltp,
                'low': ltp,
                'close': ltp,
                'volume': vol,
                'buy_vol': buy,
                'sell_vol': sell,
                'delta': candle_delta,
                'cum_delta': current_session_cum_delta,
                'footprint': [],
                'cum_volume': int(self._last_processed_cum_volume.get(symbol)) if self._last_processed_cum_volume.get(symbol) is not None else int(vol)
            }

            self._footprints[symbol] = {bucket: {'buy': buy, 'sell': sell}}
        else:
            # Update existing candle
            c['high'] = max(c['high'], ltp)
            c['low'] = min(c['low'], ltp)
            c['close'] = ltp
            c['volume'] += vol
            c['buy_vol'] += buy
            c['sell_vol'] += sell

            # Calculate new delta for this candle
            old_delta = c.get('delta', 0)
            new_delta = int(c['buy_vol']) - int(c['sell_vol'])
            c['delta'] = new_delta

            # Update session cumulative delta by the change in this candle's delta
            delta_change = new_delta - old_delta
            current_session_cum_delta = self._session_cum_delta.get(symbol, 0) + delta_change
            self._session_cum_delta[symbol] = current_session_cum_delta
            c['cum_delta'] = current_session_cum_delta

            # Update footprint
            fp = self._footprints.setdefault(symbol, {})
            if bucket not in fp:
                fp[bucket] = {'buy': 0, 'sell': 0}
            fp[bucket]['buy'] += buy
            fp[bucket]['sell'] += sell

            # Update cumulative traded volume on the candle
            if self._last_processed_cum_volume.get(symbol) is not None:
                c['cum_volume'] = int(self._last_processed_cum_volume.get(symbol))
            else:
                c['cum_volume'] = int(c.get('cum_volume', 0)) + int(vol)

        # Reconcile totals and footprint
        self._reconcile_candle_and_footprint(symbol)

        # Return a copy with symbol included for validation
        result = self._candles[symbol].copy()
        result['symbol'] = symbol
        return result

    def _determine_trade_volume(self, symbol: str, msg: dict) -> int:
        raw_trade = msg.get('last_traded_qty')
        cum = msg.get('vol_traded_today')

        # Update last cumulative volume for reference
        if isinstance(cum, (int, float)) and cum >= 0:
            self._last_cum_volume[symbol] = int(cum)

        # Try cumulative volume approach first
        if isinstance(cum, (int, float)) and cum >= 0:
            cur = int(cum)
            last = self._last_processed_cum_volume.get(symbol)

            if last is None:
                self._last_processed_cum_volume[symbol] = cur
                return int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0

            if cur < last:  # Handle reset/rollover
                self._last_processed_cum_volume[symbol] = cur
                return int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0

            delta = cur - last
            # Sanity check: accept only positive reasonable deltas. If implausible,
            # fall back to raw trade size if available to avoid losing volume.
            if delta <= 0 or delta > 2_000_000:
                raw_trade_qty = int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0
                if raw_trade_qty > 0:
                    self._last_processed_cum_volume[symbol] = cur
                    return raw_trade_qty
                return 0

            self._last_processed_cum_volume[symbol] = cur
            return int(delta)

        # Fall back to raw trade volume
        if isinstance(raw_trade, (int, float)) and raw_trade > 0:
            return int(raw_trade)

        return 0

    def _calculate_buy_sell_volume(self, msg: dict, vol: int) -> Tuple[int, int]:
        return calculate_aggressor_volumes(msg, vol)

    def _reconcile_candle_and_footprint(self, symbol: str):
        c = self._candles.get(symbol)
        if not c:
            return

        fp_map = self._footprints.setdefault(symbol, {})

        try:
            vol = int(c.get('volume', 0))
            buy = int(c.get('buy_vol', 0))
            sell = int(c.get('sell_vol', 0))
        except (ValueError, TypeError):
            return

        # Reconcile candle volume totals
        diff = vol - (buy + sell)

        if diff != 0:
            if diff < 0:  # Over-allocated
                total = buy + sell
                if total > 0:
                    a_buy, a_sell = _proportional_alloc(int(vol), [buy, sell])
                    buy = max(0, a_buy)
                    sell = max(0, a_sell)
                else:
                    buy = 0
                    sell = 0
            else:  # Under-allocated
                if buy == 0 and sell == 0:
                    o = c.get('open', 0)
                    cl = c.get('close', 0)
                    try:
                        if float(cl) > float(o):
                            buy += diff
                        elif float(cl) < float(o):
                            sell += diff
                        else:
                            half = diff // 2
                            buy += half
                            sell += diff - half
                    except (ValueError, TypeError):
                        half = diff // 2
                        buy += half
                        sell += diff - half
                else:
                    # Distribute proportionally
                    total = buy + sell
                    if total > 0:
                        add_buy, add_sell = _proportional_alloc(int(diff), [buy, sell])
                        buy += add_buy
                        sell += add_sell
                    else:
                        half = diff // 2
                        buy += half
                        sell += diff - half

        c['buy_vol'] = int(buy)
        c['sell_vol'] = int(sell)

        # Update delta and cumulative delta
        old_delta = c.get('delta', 0)
        new_delta = int(c['buy_vol']) - int(c['sell_vol'])
        c['delta'] = new_delta

        # Update session cumulative delta
        delta_change = new_delta - old_delta
        current_session_cum_delta = self._session_cum_delta.get(symbol, 0) + delta_change
        self._session_cum_delta[symbol] = current_session_cum_delta
        c['cum_delta'] = current_session_cum_delta

        # Reconcile footprint buckets
        try:
            cur_buy = sum(int(v.get('buy', 0)) for v in fp_map.values())
            cur_sell = sum(int(v.get('sell', 0)) for v in fp_map.values())
        except (ValueError, TypeError):
            cur_buy = cur_sell = 0

        tgt_buy = int(c.get('buy_vol', 0))
        tgt_sell = int(c.get('sell_vol', 0))

        d_buy = tgt_buy - cur_buy
        d_sell = tgt_sell - cur_sell

        if d_buy != 0 or d_sell != 0:
            if fp_map:
                largest_key = max(fp_map.keys(), 
                                 key=lambda k: fp_map[k].get('buy', 0) + fp_map[k].get('sell', 0))
                
                if d_buy > 0:
                    fp_map[largest_key]['buy'] = fp_map[largest_key].get('buy', 0) + d_buy
                elif d_buy < 0:
                    fp_map[largest_key]['buy'] = max(0, fp_map[largest_key].get('buy', 0) + d_buy)
                
                if d_sell > 0:
                    fp_map[largest_key]['sell'] = fp_map[largest_key].get('sell', 0) + d_sell
                elif d_sell < 0:
                    fp_map[largest_key]['sell'] = max(0, fp_map[largest_key].get('sell', 0) + d_sell)
                
                final_buy = sum(int(v.get('buy', 0)) for v in fp_map.values())
                final_sell = sum(int(v.get('sell', 0)) for v in fp_map.values())
                
                if final_buy != tgt_buy or final_sell != tgt_sell:
                    logger.warning(
                        f"Footprint reconciliation incomplete: "
                        f"buy {final_buy}/{tgt_buy}, sell {final_sell}/{tgt_sell}"
                    )
            else:
                try:
                    poc_bucket = get_bucket_key(c.get('close', 0), self.bucket_size, self.multiplier)
                except (ValueError, TypeError):
                    poc_bucket = round(float(c.get('close', 0) or 0), 2)

                fp_map[poc_bucket] = {'buy': int(tgt_buy), 'sell': int(tgt_sell)}
        else:
            total_bucket = cur_buy + cur_sell

            if total_bucket > 0:
                keys = list(fp_map.keys())
                weights_total = [int(fp_map[k].get('buy', 0)) + int(fp_map[k].get('sell', 0)) for k in keys]

                add_buys = _proportional_alloc(int(d_buy), weights_total) if d_buy != 0 else [0] * len(keys)
                add_sells = _proportional_alloc(int(d_sell), weights_total) if d_sell != 0 else [0] * len(keys)

                for idx, k in enumerate(keys):
                    v = fp_map[k]
                    v['buy'] = max(0, int(v.get('buy', 0)) + add_buys[idx])
                    v['sell'] = max(0, int(v.get('sell', 0)) + add_sells[idx])
            else:
                try:
                    poc_bucket = get_bucket_key(c.get('close', 0), self.bucket_size, self.multiplier)
                except (ValueError, TypeError):
                    poc_bucket = round(float(c.get('close', 0) or 0), 2)

                fp_map.setdefault(poc_bucket, {'buy': 0, 'sell': 0})
                fp_map[poc_bucket]['buy'] = int(tgt_buy)
                fp_map[poc_bucket]['sell'] = int(tgt_sell)

        # Build final footprint array
        c['footprint'] = build_footprint_from_map(c, fp_map, self.bucket_size * self.multiplier)

    def _is_first_candle_of_day(self, time_bin: int) -> bool:
        try:
            dt = datetime.fromtimestamp(time_bin)
            if self.timeframe in ['1m', '5m', '15m']:
                return dt.hour == MARKET_OPEN_HOUR and dt.minute == MARKET_OPEN_MINUTE
            return dt.hour == MARKET_OPEN_HOUR and dt.minute <= MARKET_OPEN_MINUTE + 5
        except (ValueError, OSError):
            return False

# ----------------- 5s Tick Aggregator -----------------

class TickToBucket5s:
    """Aggregates ticks into 5-second buckets. Outputs rows compatible with process_hist_data input."""

    def __init__(self, bucket_size: float = 0.05, multiplier: int = 100):
        self.bucket_size = float(bucket_size)
        self.multiplier = int(multiplier)

        self._buckets: Dict[Tuple[int, str], Dict] = {}
        self._recent_trades: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._last_processed_cum_volume: Dict[str, int] = {}

    def process_tick(self, msg: dict) -> Optional[Dict]:
        symbol = msg.get('symbol')
        ltp = msg.get('ltp')
        ts = msg.get('exch_feed_time') or msg.get('last_traded_time')

        if not symbol or ltp is None or ts is None:
            return None

        ts = normalize_timestamp_to_seconds(ts)
        if ts is None:
            return None

        try:
            ltp = float(ltp)
        except (ValueError, TypeError):
            return None

        # 5-second bin
        time_bin = calculate_aligned_time_bin(ts, 5)

        # determine volume
        vol = self._determine_trade_volume(symbol, msg)
        if vol <= 0 or vol > 5_000_000:
            return None

        # Check for duplicate trades
        trade_key = (ts, ltp, self._last_processed_cum_volume.get(symbol, 0))
        if trade_key in self._recent_trades[symbol]:
            return None

        self._recent_trades[symbol].append(trade_key)

        # allocate buy/sell
        buy, sell = calculate_aggressor_volumes(msg, vol)

        key = (time_bin, symbol)
        b = self._buckets.get(key)

        if b is None:
            b = {
                'timestamp': time_bin,
                'symbol': symbol,
                'open': ltp,
                'high': ltp,
                'low': ltp,
                'close': ltp,
                'volume': vol,
                'buy_vol': buy,
                'sell_vol': sell,
                'cum_volume': int(self._last_processed_cum_volume.get(symbol)) if self._last_processed_cum_volume.get(symbol) is not None else int(vol)
            }
            self._buckets[key] = b
        else:
            b['high'] = max(b['high'], ltp)
            b['low'] = min(b['low'], ltp)
            b['close'] = ltp
            b['volume'] += vol
            b['buy_vol'] += buy
            b['sell_vol'] += sell
            if self._last_processed_cum_volume.get(symbol) is not None:
                b['cum_volume'] = int(self._last_processed_cum_volume.get(symbol))
            else:
                b['cum_volume'] = int(b.get('cum_volume', 0)) + int(vol)

        return b.copy()

    def _determine_trade_volume(self, symbol: str, msg: dict) -> int:
        raw_trade = msg.get('last_traded_qty')
        cum = msg.get('vol_traded_today')

        if isinstance(cum, (int, float)) and cum >= 0:
            self._last_processed_cum_volume.setdefault(symbol, int(cum))

        if isinstance(cum, (int, float)) and cum >= 0:
            cur = int(cum)
            last = self._last_processed_cum_volume.get(symbol)

            if last is None:
                self._last_processed_cum_volume[symbol] = cur
                return int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0

            if cur < last:  # Handle reset/rollover
                self._last_processed_cum_volume[symbol] = cur
                return int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0

            delta = cur - last
            if delta <= 0 or delta > 2_000_000:
                raw_trade_qty = int(raw_trade) if isinstance(raw_trade, (int, float)) and raw_trade > 0 else 0
                if raw_trade_qty > 0:
                    self._last_processed_cum_volume[symbol] = cur
                    return raw_trade_qty
                return 0

            self._last_processed_cum_volume[symbol] = cur
            return int(delta)

        if isinstance(raw_trade, (int, float)) and raw_trade > 0:
            return int(raw_trade)

        return 0

    def flush(self) -> List[Dict]:
        """Return all current buckets as a list and clear"""
        rows = list(self._buckets.values())
        self._buckets.clear()
        return rows

# ----------------- Historical processing (Polars-based) -----------------

def process_hist_data(df: pl.DataFrame, timeframe: str, symbol_col: Optional[str] = None,
                      data_frame: bool = False, footprint: bool = True,
                      bucket_size: float = 0.05, multiplier: int = 100, preserve_live_data: bool = True):

    if not isinstance(df, pl.DataFrame):
        raise ValueError('Input must be a Polars DataFrame')

    if 'timestamp' not in df.columns:
        raise ValueError('DataFrame must have a timestamp column')

    seconds = _INTERVAL_MAP.get(timeframe, 300)

    # If df already contains buy_vol/sell_vol we should respect them; otherwise compute heuristics
    has_precomputed = 'buy_vol' in df.columns and 'sell_vol' in df.columns
    use_precomputed = has_precomputed and preserve_live_data

    duplicate_cols = ['timestamp']
    group_cols = ['time']

    if symbol_col and symbol_col in df.columns:
        duplicate_cols.append(symbol_col)
        group_cols.append(symbol_col)

    buy_expr = (
        pl.when(pl.col('close') > pl.col('open')).then(pl.col('volume'))
        .when((pl.col('close') == pl.col('open')) & (pl.col('close') > pl.col('close').shift(1)))
        .then(pl.col('volume'))
        .otherwise(0)
    )

    sell_expr = (
        pl.when(pl.col('close') < pl.col('open')).then(pl.col('volume'))
        .when((pl.col('close') == pl.col('open')) & (pl.col('close') < pl.col('close').shift(1)))
        .then(pl.col('volume'))
        .otherwise(0)
    )

    ldf = df.lazy().with_columns([
        pl.col(symbol_col).cast(pl.Categorical) if symbol_col and symbol_col in df.columns else pl.lit(None),
        pl.col('timestamp').cast(pl.Int64)
    ])

    ldf = ldf.unique(subset=duplicate_cols, keep='first').with_columns(
        [(pl.col('timestamp') // seconds * seconds).alias('time')]
    )

    if symbol_col and symbol_col in df.columns:
        ldf = ldf.sort([symbol_col, 'timestamp'])
    else:
        ldf = ldf.sort('timestamp')

    if not use_precomputed:
        ldf = ldf.with_columns([buy_expr.alias('buy_vol'), sell_expr.alias('sell_vol')])

    agg = [
        pl.col('open').first().alias('open'),
        pl.col('high').max().alias('high'),
        pl.col('low').min().alias('low'),
        pl.col('close').last().alias('close'),
        pl.col('volume').sum().alias('volume'),
        pl.col('buy_vol').sum().alias('buy_vol'),
        pl.col('sell_vol').sum().alias('sell_vol')
    ]

    grouped = ldf.group_by(group_cols).agg(agg).with_columns(
        [(pl.col('buy_vol') - pl.col('sell_vol')).alias('delta')]
    )

    out_cols = group_cols + ['open', 'high', 'low', 'close', 'volume', 'buy_vol', 'sell_vol', 'delta']
    unique_subset = ['time', symbol_col] if (symbol_col and symbol_col in df.columns) else ['time']
    output_df = grouped.select(out_cols).collect().sort('time').unique(subset=unique_subset, keep='first')

    out_rows = output_df.to_dicts()

    # Reconcile buy/sell totals
    for r in out_rows:
        try:
            vol = int(r.get('volume') or 0)
            buy = int(r.get('buy_vol') or 0)
            sell = int(r.get('sell_vol') or 0)
        except (ValueError, TypeError):
            continue

        diff = vol - (buy + sell)

        if diff == 0:
            r['delta'] = r.get('delta', buy - sell)
            continue

        if diff < 0:  # Over-allocated
            total = buy + sell
            if total > 0:
                a_buy, a_sell = _proportional_alloc(int(vol), [buy, sell])
                r['buy_vol'] = max(0, a_buy)
                r['sell_vol'] = max(0, a_sell)
            else:
                r['buy_vol'] = 0
                r['sell_vol'] = 0
        else:  # Under-allocated
            if buy == 0 and sell == 0:
                o = r.get('open') or 0
                c = r.get('close') or 0
                try:
                    if float(c) > float(o):
                        r['buy_vol'] = buy + diff
                        r['sell_vol'] = sell
                    elif float(c) < float(o):
                        r['sell_vol'] = sell + diff
                        r['buy_vol'] = buy
                    else:
                        half = diff // 2
                        r['buy_vol'] = buy + half
                        r['sell_vol'] = sell + (diff - half)
                except (ValueError, TypeError):
                    half = diff // 2
                    r['buy_vol'] = buy + half
                    r['sell_vol'] = sell + (diff - half)
            else:
                total = buy + sell
                if total > 0:
                    try:
                        add_buy = int(round(diff * (buy / total)))
                        add_sell = diff - add_buy
                        r['buy_vol'] = buy + add_buy
                        r['sell_vol'] = sell + add_sell
                    except ZeroDivisionError:
                        half = diff // 2
                        r['buy_vol'] = buy + half
                        r['sell_vol'] = sell + (diff - half)
                else:
                    half = diff // 2
                    r['buy_vol'] = buy + half
                    r['sell_vol'] = sell + (diff - half)

        try:
            r['delta'] = int(r.get('buy_vol', 0)) - int(r.get('sell_vol', 0))
        except (ValueError, TypeError):
            pass

    # --- compute cumulative delta and cumulative volume per symbol per trading day ---
    try:
        grouped_rows = {}
        for r in out_rows:
            sym_key = r.get(symbol_col) if (symbol_col and symbol_col in r) else None
            grouped_rows.setdefault(sym_key, []).append(r)

        for sym_key, rows in grouped_rows.items():
            rows.sort(key=lambda x: int(x.get('time', 0)))

            cum_delta = 0
            cum_vol = 0
            current_trading_day = None

            for r in rows:
                try:
                    candle_time = int(r.get('time', 0))
                    dt = datetime.fromtimestamp(candle_time)
                    trading_day = get_market_open_timestamp(dt)
                except (ValueError, OSError, TypeError):
                    trading_day = None

                # Reset cumulative counters at the start of a new trading day
                if current_trading_day is None or trading_day != current_trading_day:
                    cum_delta = 0
                    cum_vol = 0
                    current_trading_day = trading_day

                try:
                    delta_val = int(r.get('delta', 0))
                except (ValueError, TypeError):
                    delta_val = 0

                try:
                    vol_val = int(r.get('volume', 0))
                except (ValueError, TypeError):
                    vol_val = 0

                cum_delta += delta_val
                cum_vol += vol_val

                r['cum_delta'] = int(cum_delta)
                r['cum_volume'] = int(cum_vol)
                r['vol_traded_today'] = int(cum_vol)
                r['last_cum_volume'] = int(cum_vol)
    except Exception:
        logger.exception("Error calculating cumulative delta/volume in historical data")
        pass

    # Footprint calculation
    if footprint:
        bucket = bucket_size * multiplier

        if bucket <= 0:
            if data_frame:
                try:
                    return pl.DataFrame(out_rows)
                except Exception:
                    return out_rows
            return clean_nans(out_rows)

        df_exp = (
            df.lazy()
            .with_columns([
                ((pl.col('timestamp') // seconds) * seconds).alias('time'),
                (pl.col('buy_vol') if 'buy_vol' in df.columns else buy_expr).alias('buy_vol'),
                (pl.col('sell_vol') if 'sell_vol' in df.columns else sell_expr).alias('sell_vol')
            ])
            .collect()
            .with_columns([
                (
                    (pl.col('close') / (pl.lit(bucket_size * multiplier))).floor() * pl.lit(bucket_size * multiplier)
                ).round(2).alias('price_bucket')
            ])
        )

        fp_group_cols = ['time', 'price_bucket']
        if symbol_col and symbol_col in df.columns:
            fp_group_cols.append(symbol_col)

        fp_df = (
            df_exp.group_by(fp_group_cols)
            .agg([
                pl.col('buy_vol').sum().alias('buyVolume'),
                pl.col('sell_vol').sum().alias('sellVolume')
            ])
            .sort(['time', 'price_bucket'])
        )

        fp_dict = {}
        sym_present = symbol_col and symbol_col in fp_df.columns

        for row in fp_df.iter_rows(named=True):
            key = (row['time'], row[symbol_col]) if sym_present else (row['time'],)
            fp_dict.setdefault(key, {})[float(row['price_bucket'])] = {
                'buyVolume': int(row['buyVolume']),
                'sellVolume': int(row['sellVolume'])
            }

        for r in out_rows:
            key = (r['time'], r.get(symbol_col)) if (symbol_col and symbol_col in r) else (r['time'],)
            fp_data = fp_dict.get(key, {})

            fp_map = {}
            for price_level, data in fp_data.items():
                try:
                    p = float(price_level)
                except (ValueError, TypeError):
                    continue
                fp_map[round(p, 2)] = {
                    'buy': int(data.get('buyVolume', 0)),
                    'sell': int(data.get('sellVolume', 0))
                }

            bucket_value = bucket_size * multiplier
            r['footprint'] = build_footprint_from_map(r, fp_map, bucket_value)

    if data_frame:
        try:
            return pl.DataFrame(out_rows)
        except Exception:
            return out_rows

    return clean_nans(out_rows)

# ----------------- helpers for footprint building -----------------

def build_footprint_from_map(candle: Dict, fp_map: Dict[float, Dict[str, int]], bucket_value: float) -> List[Dict]:
    if bucket_value <= 0 or not fp_map:
        return []

    low = candle['low']
    high = candle['high']

    try:
        min_bucket = math.floor(float(low) / bucket_value) * bucket_value
        max_bucket = math.floor(float(high) / bucket_value) * bucket_value
    except (ValueError, TypeError):
        return []

    ladder = []

    try:
        if bucket_value <= 0:
            return []

        min_idx = int(math.floor(float(min_bucket) / bucket_value))
        max_idx = int(math.floor(float(max_bucket) / bucket_value))

        max_iters = 5000
        count = max_idx - min_idx + 1
        if count <= 0:
            return []
        if count > max_iters:
            logger.warning(
                f"Footprint truncation: range needs {count} buckets, "
                f"max is {max_iters}. Centering around POC."
            )
            mid = (min_idx + max_idx) // 2
            start = mid - (max_iters // 2)
            end = start + max_iters - 1
            min_idx, max_idx = start, end

        for idx in range(min_idx, max_idx + 1):
            level = round(idx * bucket_value, 2)
            entry = _get_fp_entry_with_tolerance(level, fp_map, tolerance=1e-6)
            ladder.append({
                'priceLevel': level,
                'buyVolume': int(entry.get('buy', 0)),
                'sellVolume': int(entry.get('sell', 0))
            })
    except (ValueError, TypeError):
        return []

    ladder = sorted(ladder, key=lambda x: x['priceLevel'], reverse=True)

    try:
        cur_buy = sum(int(item.get('buyVolume', 0)) for item in ladder)
        cur_sell = sum(int(item.get('sellVolume', 0)) for item in ladder)
        tgt_buy = int(candle.get('buy_vol', 0))
        tgt_sell = int(candle.get('sell_vol', 0))
        
        d_buy = tgt_buy - cur_buy
        d_sell = tgt_sell - cur_sell

        if d_buy != 0 or d_sell != 0:
            total_volume = cur_buy + cur_sell

            if total_volume > 0:
                weights = [item['buyVolume'] + item['sellVolume'] for item in ladder]
                add_buys = _proportional_alloc(int(d_buy), weights) if d_buy != 0 else [0] * len(ladder)
                add_sells = _proportional_alloc(int(d_sell), weights) if d_sell != 0 else [0] * len(ladder)

                for idx, item in enumerate(ladder):
                    item['buyVolume'] = max(0, int(item['buyVolume'] + add_buys[idx]))
                    item['sellVolume'] = max(0, int(item['sellVolume'] + add_sells[idx]))

            cur_buy = sum(int(item.get('buyVolume', 0)) for item in ladder)
            cur_sell = sum(int(item.get('sellVolume', 0)) for item in ladder)

            if ladder and (cur_buy != tgt_buy or cur_sell != tgt_sell):
                largest_idx = max(range(len(ladder)), 
                                key=lambda i: ladder[i]['buyVolume'] + ladder[i]['sellVolume'])
                ladder[largest_idx]['buyVolume'] = max(0, 
                    int(ladder[largest_idx]['buyVolume'] + (tgt_buy - cur_buy)))
                ladder[largest_idx]['sellVolume'] = max(0, 
                    int(ladder[largest_idx]['sellVolume'] + (tgt_sell - cur_sell)))
    except (ValueError, TypeError, IndexError):
        pass

    return ladder

# ----------------- utility -----------------

def clean_nans(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    if obj is None:
        return None

    if isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [clean_nans(x) for x in obj]

    return obj

# ----------------- Backwards compatible APIs -----------------

def process_live_data(msg, timeframe, bucket_size, multiplier, hist_last_candle: Optional[Dict] = None):
    """Process a live tick message."""
    try:
        if not isinstance(msg, dict) or not msg.get('symbol') or not msg.get('ltp'):
            return None

        bucket_size = float(bucket_size)
        multiplier = int(multiplier)
        symbol = msg.get('symbol')

        key = f"{symbol}_{timeframe}_{bucket_size}_{multiplier}"

        if key not in _candle_state:
            _candle_state[key] = CandleAggregator(timeframe, bucket_size, multiplier)

        agg = _candle_state[key]

        try:
            if isinstance(hist_last_candle, dict):
                h = hist_last_candle
                h_time = int(h.get('time') or h.get('timestamp') or 0)

                if h_time > 0:
                    cur_c = agg._candles.get(symbol)
                    need_seed = (cur_c is None) or (int(cur_c.get('time', 0)) != int(h_time))

                    if need_seed:
                        seeded = {
                            'time': int(h_time),
                            'open': float(h.get('open', 0.0) or 0.0),
                            'high': float(h.get('high', h.get('close', 0.0) or 0.0)),
                            'low': float(h.get('low', h.get('close', 0.0) or 0.0)),
                            'close': float(h.get('close', 0.0) or 0.0),
                            'volume': int(h.get('volume', 0) or 0),
                            'buy_vol': int(h.get('buy_vol', 0) or 0),
                            'sell_vol': int(h.get('sell_vol', 0) or 0),
                            'delta': int(h.get('delta', 0) or 0),
                            'cum_delta': int(h.get('cum_delta', 0) or 0),
                            'footprint': h.get('footprint', []) or []
                        }

                        agg._candles[symbol] = seeded
                        agg._session_cum_delta[symbol] = int(h.get('cum_delta', 0) or 0)
                        agg._current_candle_time[symbol] = h_time

                        try:
                            trading_day = get_market_open_timestamp(datetime.fromtimestamp(h_time))
                            agg._last_trading_day_per_symbol[symbol] = trading_day
                        except (ValueError, OSError):
                            pass

                        fp_map = {}
                        try:
                            fp_list = h.get('footprint') or []
                            for item in fp_list:
                                price = (item.get('priceLevel') if 'priceLevel' in item 
                                       else item.get('price') if 'price' in item else None)
                                buyv = (item.get('buyVolume') if 'buyVolume' in item 
                                       else item.get('buy', 0))
                                sellv = (item.get('sellVolume') if 'sellVolume' in item 
                                        else item.get('sell', 0))

                                if price is None:
                                    continue

                                try:
                                    p = float(price)
                                except (ValueError, TypeError):
                                    continue

                                fp_map[round(p, 2)] = {'buy': int(buyv or 0), 'sell': int(sellv or 0)}
                        except (ValueError, TypeError):
                            fp_map = {}

                        if fp_map:
                            agg._footprints[symbol] = fp_map

                        try:
                            agg._last_ltp[symbol] = float(seeded.get('close', 0.0) or 0.0)
                        except (ValueError, TypeError):
                            pass

                        hist_cum = None
                        for k in ('cum_volume', 'vol_traded_today', 'last_cum_volume', 'cum_vol'):
                            if k in h and isinstance(h.get(k), (int, float)):
                                hist_cum = int(h.get(k))
                                break
                        try:
                            if isinstance(hist_cum, int) and hist_cum >= 0:
                                agg._last_processed_cum_volume[symbol] = hist_cum
                                agg._last_cum_volume[symbol] = hist_cum
                                seeded['cum_volume'] = hist_cum
                                agg._recent_trades.setdefault(symbol, deque(maxlen=200)).clear()
                        except (ValueError, TypeError):
                            pass
        except (ValueError, TypeError):
            pass

        try:
            seeded_c = agg._candles.get(symbol)
            if isinstance(seeded_c, dict):
                seed_cum = seeded_c.get('cum_volume') or seeded_c.get('vol_traded_today') or seeded_c.get('last_cum_volume') or seeded_c.get('volume')
                incoming_cum = None
                for k in ('vol_traded_today', 'last_cum_volume', 'cum_volume', 'cum_vol'):
                    if k in msg and isinstance(msg.get(k), (int, float)):
                        incoming_cum = int(msg.get(k))
                        break

                if incoming_cum is not None and seed_cum is not None and int(incoming_cum) == int(seed_cum):
                    result = seeded_c.copy()
                    result['symbol'] = symbol
                    return result
        except (ValueError, TypeError):
            pass

        return agg.process_tick(msg)
    except (ValueError, TypeError):
        return None

def clear_processor_state(symbol, timeframe, bucket_size, multiplier):
    key = f"{symbol}_{timeframe}_{bucket_size}_{multiplier}"
    if key in _candle_state:
        del _candle_state[key]
        return True
    return False
