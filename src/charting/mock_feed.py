import time
import random
import threading
from datetime import datetime
import json

class MockFyersFeed:
    """
    Simulates the Fyers Versova WebSocket feed.
    Generates realistic L2 order book data and trades.
    """
    def __init__(self, symbols, on_message_callback=None, log_callback=None):
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self.on_message_callback = on_message_callback
        self.log_callback = log_callback or print
        self.running = False
        self.thread = None
        
        # State per symbol
        self.state = {}
        for sym in self.symbols:
            base_price = 25000.0
            if "BANKNIFTY" in sym: base_price = 50000.0
            elif "NIFTY" in sym: base_price = 25000.0
            elif "RELIANCE" in sym: base_price = 2800.0
            elif "SBIN" in sym: base_price = 800.0

            self.state[sym] = {
                'ltp': base_price,
                'vol_traded_today': 100000,
                'bids': [],
                'asks': [],
                'tbq': 500000,
                'tsq': 550000
            }
            self._generate_initial_book(sym)

    def _generate_initial_book(self, symbol):
        """Generates an initial 50-level order book around the LTP."""
        s = self.state[symbol]
        ltp = s['ltp']
        
        s['bids'] = []
        s['asks'] = []
        
        current_bid = ltp - 0.5
        current_ask = ltp + 0.5
        
        for i in range(50):
            # Bids (decreasing price)
            s['bids'].append({
                'price': current_bid - (i * 0.5),
                'qty': random.randint(50, 5000),
                'orders': random.randint(1, 20),
                'level': i
            })
            # Asks (increasing price)
            s['asks'].append({
                'price': current_ask + (i * 0.5),
                'qty': random.randint(50, 5000),
                'orders': random.randint(1, 20),
                'level': i
            })

    def log(self, message):
        if self.log_callback:
            self.log_callback(f"[MockFeed] {message}")

    def subscribe(self, symbols):
        if not isinstance(symbols, list):
            symbols = [symbols]
        for sym in symbols:
            if sym not in self.symbols:
                base_price = 25000.0
                if "BANKNIFTY" in sym: base_price = 50000.0
                elif "NIFTY" in sym: base_price = 25000.0
                elif "RELIANCE" in sym: base_price = 2800.0
                elif "SBIN" in sym: base_price = 800.0

                self.symbols.append(sym)
                self.state[sym] = {
                    'ltp': base_price,
                    'vol_traded_today': 100000,
                    'bids': [],
                    'asks': [],
                    'tbq': 500000,
                    'tsq': 550000
                }
                self._generate_initial_book(sym)
        self.log(f"Subscribed to {symbols}")

    def unsubscribe(self, symbols):
        if not isinstance(symbols, list):
            symbols = [symbols]
        for sym in symbols:
            if sym in self.symbols:
                self.symbols.remove(sym)
        self.log(f"Unsubscribed from {symbols}")

    def _simulate_tick(self, symbol):
        """Generates a new tick modifying the state slightly."""
        s = self.state[symbol]
        
        # Random walk for LTP (tick size 0.5)
        move = random.choice([-0.5, 0.0, 0.5])
        s['ltp'] += move
        
        # Simulate a trade volume
        trade_vol = random.randint(50, 1000)
        s['vol_traded_today'] += trade_vol
        
        # Shift book if LTP moved
        if move != 0:
            self._generate_initial_book(symbol)
        else:
            # Randomly perturb top 5 levels
            for i in range(5):
                s['bids'][i]['qty'] = max(50, s['bids'][i]['qty'] + random.randint(-500, 500))
                s['asks'][i]['qty'] = max(50, s['asks'][i]['qty'] + random.randint(-500, 500))

        # Format message matching Fyers protobuf output structure
        msg = {
            'symbol': symbol,
            'timestamp': int(time.time()),
            'ltp': s['ltp'],
            'vol_traded_today': s['vol_traded_today'],
            'last_traded_qty': trade_vol,
            'tot_buy_qty': sum(b['qty'] for b in s['bids']),
            'tot_sell_qty': sum(a['qty'] for a in s['asks']),
            'bids': s['bids'],
            'asks': s['asks']
        }
        return msg

    def _run_loop(self):
        self.log("Mock feed started")
        while self.running:
            for sym in self.symbols:
                msg = self._simulate_tick(sym)
                if self.on_message_callback:
                    # In real Fyers, we get a list of dicts or custom objects
                    # We will pass a dict representing the tick
                    self.on_message_callback({'type': 'live_tick', 'data': msg})
            
            # Emit 2-3 ticks per second
            time.sleep(random.uniform(0.3, 0.6))
        self.log("Mock feed stopped")

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

if __name__ == "__main__":
    def print_msg(msg):
        print(f"[{datetime.now().time()}] TICK: {msg['data']['symbol']} @ {msg['data']['ltp']} Vol: {msg['data']['last_traded_qty']}")
    
    feed = MockFyersFeed(["NSE:NIFTY26JANFUT"], on_message_callback=print_msg)
    feed.start()
    time.sleep(5)
    feed.stop()
