import time
import json
import threading
import websocket
from .protobuf import msg_pb2

class FyersVersovaEngine:
    def __init__(self, auth_token, api_key, symbols, on_message_callback=None, log_callback=None):
        print("DEBUG: Loading SYNC FyersVersovaEngine")
        self.auth_token = auth_token
        self.api_key = api_key
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self.on_message_callback = on_message_callback
        self.log_callback = log_callback or print
        
        self.websocket_url = "wss://rtsocket-api.fyers.in/versova"
        self.ws = None
        self.running = False
        self.thread = None
        
        # Order book storage
        self.order_books = {}

    def log(self, message):
        if self.log_callback:
            self.log_callback(f"[Versova] {message}")

    def subscribe(self, symbols):
        """Subscribe to market data for new symbols"""
        if not isinstance(symbols, list):
            symbols = [symbols]
            
        # Update internal list
        for sym in symbols:
            if sym not in self.symbols:
                self.symbols.append(sym)
        
        msg = {
            "type": 1,
            "data": {
                "subs": 1,
                "symbols": symbols,
                "mode": "depth",
                "channel": "1"
            }
        }
        self._send(msg)

    def unsubscribe(self, symbols):
        """Unsubscribe from symbols"""
        if not isinstance(symbols, list):
            symbols = [symbols]
            
        for sym in symbols:
            if sym in self.symbols:
                self.symbols.remove(sym)
                
        msg = {
            "type": 1,
            "data": {
                "subs": 0,
                "symbols": symbols
            }
        }
        self._send(msg)

    def _send(self, msg):
        """Send message to websocket safely"""
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(json.dumps(msg))
            except Exception as e:
                self.log(f"Send error: {e}")

    def update_order_book(self, ticker, bids, asks, tbq, tsq, ltp, vol_traded_today, timestamp, is_snapshot):
        """Enhanced order book update with guaranteed 50-level depth maintenance"""
        if ticker not in self.order_books:
            # Initialize empty order book with 50 levels
            self.order_books[ticker] = {
                'bids': {i: {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i} for i in range(50)},
                'asks': {i: {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i} for i in range(50)},
                'tbq': 0,
                'tsq': 0,
                'ltp': 0.0,
                'vol_traded_today': 0,
                'timestamp': 0,
                'initialized': False
            }
        
        book = self.order_books[ticker]
        book['tbq'] = tbq
        book['tsq'] = tsq
        if ltp is not None: book['ltp'] = ltp
        if vol_traded_today is not None: book['vol_traded_today'] = vol_traded_today
        book['timestamp'] = timestamp
        
        first_update = not book.get('initialized', False)
        
        if is_snapshot or first_update:
            if first_update:
                # Only reset on very first update
                for i in range(50):
                    book['bids'][i] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i}
                    book['asks'][i] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i}
        
        # Process bid updates
        for bid in bids:
            level = bid['level']
            if 0 <= level < 50:
                old_data = book['bids'][level]
                
                if bid['price'] == 0.0 and bid['qty'] > 0:
                    if old_data['price'] > 0:
                        book['bids'][level] = {
                            'price': old_data['price'], 
                            'qty': bid['qty'],
                            'orders': bid['orders'], 
                            'level': level
                        }
                elif bid['qty'] == 0:
                    if bid['price'] == 0.0 and old_data['price'] > 0:
                        book['bids'][level] = {
                            'price': old_data['price'], 
                            'qty': 0, 
                            'orders': bid['orders'], 
                            'level': level
                        }
                    elif bid['price'] > 0:
                        book['bids'][level] = bid
                    else:
                        if old_data['price'] > 0:
                            book['bids'][level] = {
                                'price': old_data['price'], 
                                'qty': 0, 
                                'orders': bid['orders'], 
                                'level': level
                            }
                        else:
                            book['bids'][level] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': level}
                else:
                    book['bids'][level] = bid
        
        # Process ask updates
        for ask in asks:
            level = ask['level']
            if 0 <= level < 50:
                old_data = book['asks'][level]
                
                if ask['price'] == 0.0 and ask['qty'] > 0:
                    if old_data['price'] > 0:
                        book['asks'][level] = {
                            'price': old_data['price'], 
                            'qty': ask['qty'],
                            'orders': ask['orders'], 
                            'level': level
                        }
                elif ask['qty'] == 0:
                    if ask['price'] == 0.0 and old_data['price'] > 0:
                        book['asks'][level] = {
                            'price': old_data['price'], 
                            'qty': 0, 
                            'orders': ask['orders'], 
                            'level': level
                        }
                    elif ask['price'] > 0:
                        book['asks'][level] = ask
                    else:
                        if old_data['price'] > 0:
                            book['asks'][level] = {
                                'price': old_data['price'], 
                                'qty': 0, 
                                'orders': ask['orders'], 
                                'level': level
                            }
                        else:
                            book['asks'][level] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': level}
                else:
                    book['asks'][level] = ask
        
        book['initialized'] = True

    def calculate_imbalance(self, ticker, depth):
        """Calculate buy/sell imbalance for a specific depth (e.g., 10, 20, 50 levels)"""
        if ticker not in self.order_books:
            return 0.0, 0.0, 0.0
            
        book = self.order_books[ticker]
        
        # Filter and sort bids (descending) and asks (ascending)
        active_bids = sorted([b for b in book['bids'].values() if b['price'] > 0], key=lambda x: x['price'], reverse=True)
        active_asks = sorted([a for a in book['asks'].values() if a['price'] > 0], key=lambda x: x['price'])
        
        bid_qty = sum(b['qty'] for b in active_bids[:depth])
        ask_qty = sum(a['qty'] for a in active_asks[:depth])
        
        total = bid_qty + ask_qty
        imbalance = (bid_qty - ask_qty) / total if total > 0 else 0.0
        
        return float(bid_qty), float(ask_qty), round(float(imbalance), 4)

    def get_market_sentiment(self, tbq, tsq):
        """Calculate market sentiment based on Total Buy/Sell Quantity (Stable)"""
        total = tbq + tsq
        if total == 0:
            return 0.0
        return round((tbq - tsq) / total, 4)

    def get_full_order_book(self, ticker):
        """Get the complete 50-level order book for display with proper depth reconstruction and imbalance metrics"""
        if ticker not in self.order_books:
            return None
        
        book = self.order_books[ticker]
        
        # Get all bid levels with valid prices
        raw_bids = []
        for i in range(50):
            bid = book['bids'][i]
            if bid['price'] > 0:
                raw_bids.append(bid)
        
        # Sort bids by price (highest first)
        raw_bids.sort(key=lambda x: x['price'], reverse=True)
        active_bids = []
        for i, bid in enumerate(raw_bids[:50]):
            active_bids.append({
                'price': bid['price'],
                'qty': bid['qty'],
                'orders': bid['orders'],
                'level': i
            })
        
        # Get all ask levels with valid prices
        raw_asks = []
        for i in range(50):
            ask = book['asks'][i]
            if ask['price'] > 0:
                raw_asks.append(ask)
        
        # Sort asks by price (lowest first)
        raw_asks.sort(key=lambda x: x['price'])
        active_asks = []
        for i, ask in enumerate(raw_asks[:50]):
            active_asks.append({
                'price': ask['price'],
                'qty': ask['qty'],
                'orders': ask['orders'],
                'level': i
            })
        
        # Calculate Imbalances for 10, 20, 50 levels
        bq10, aq10, imb10 = self.calculate_imbalance(ticker, 10)
        bq20, aq20, imb20 = self.calculate_imbalance(ticker, 20)
        bq50, aq50, imb50 = self.calculate_imbalance(ticker, 50)
        
        # Market Sentiment
        sentiment = self.get_market_sentiment(book['tbq'], book['tsq'])
        
        return {
            'ticker': ticker,
            'symbol': ticker, # Legacy support
            'ltp': book.get('ltp', 0.0),
            'vol_traded_today': book.get('vol_traded_today', 0),
            'last_traded_qty': 0, # Should be derived but for now 0
            'tbq': book['tbq'],
            'tsq': book['tsq'],
            'sentiment': sentiment,
            'timestamp': book['timestamp'],
            'imbalance_10': imb10,
            'imbalance_20': imb20,
            'imbalance_50': imb50,
            'bid_qty_50': bq50,
            'ask_qty_50': aq50,
            'bids': active_bids,
            'asks': active_asks,
            'bidprice': [bid['price'] for bid in active_bids],
            'askprice': [ask['price'] for ask in active_asks],
            'bidqty': [bid['qty'] for bid in active_bids],
            'askqty': [ask['qty'] for ask in active_asks],
            'bidordn': [bid['orders'] for bid in active_bids],
            'askordn': [ask['orders'] for ask in active_asks]
        }

    def process_market_depth(self, message_bytes):
        """Process market depth protobuf message"""
        try:
            socket_message = msg_pb2.SocketMessage()
            socket_message.ParseFromString(message_bytes)
            
            if socket_message.error:
                self.log(f"Error in socket message: {socket_message.msg}")
                return None
                
            market_data = {}
            for ticker, feed in socket_message.feeds.items():
                timestamp = feed.feed_time.value if feed.feed_time else None
                tbq = feed.depth.tbq.value if feed.depth.tbq else 0
                tsq = feed.depth.tsq.value if feed.depth.tsq else 0
                is_snapshot = socket_message.snapshot
                
                # Extract Quote Data
                ltp = feed.quote.ltp.value / 100.0 if feed.quote and feed.quote.ltp else None
                vtt = feed.quote.vtt.value if feed.quote and feed.quote.vtt else None
                
                update_bids = []
                for bid in feed.depth.bids:
                    update_bids.append({
                        'price': bid.price.value / 100.0,
                        'qty': bid.qty.value,
                        'orders': bid.nord.value,
                        'level': bid.num.value
                    })
                
                update_asks = []
                for ask in feed.depth.asks:
                    update_asks.append({
                        'price': ask.price.value / 100.0,
                        'qty': ask.qty.value,
                        'orders': ask.nord.value,
                        'level': ask.num.value
                    })
                
                self.update_order_book(ticker, update_bids, update_asks, tbq, tsq, ltp, vtt, timestamp, is_snapshot)
                
                full_book = self.get_full_order_book(ticker)
                if full_book:
                    market_data[ticker] = full_book
            
            return market_data if len(market_data) > 0 else None
            
        except Exception as e:
            self.log(f"Error processing market depth: {e}")
            return None

    def _on_open(self, ws):
        self.log("Connected to Fyers Versova")
        self.running = True
        
        # Initial Subscribe
        subscribe_msg = {
            "type": 1,
            "data": {
                "subs": 1,
                "symbols": self.symbols,
                "mode": "depth",
                "channel": "1"
            }
        }
        self._send(subscribe_msg)
        
        # Resume
        resume_msg = {
            "type": 2,
            "data": {
                "resumeChannels": ["1"],
                "pauseChannels": []
            }
        }
        self._send(resume_msg)

    def _on_message(self, ws, message):
        if isinstance(message, bytes):
            market_data = self.process_market_depth(message)
            if market_data and self.on_message_callback:
                self.on_message_callback(market_data)

    def _on_error(self, ws, error):
        self.log(f"Connection error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.log("Connection closed")
        self.running = False

    def start(self):
        """Start the WebSocket in a background thread"""
        def run():
            auth_header = f"{self.api_key}:{self.auth_token}"
            
            while True: # Auto-reconnect loop
                try:
                    self.ws = websocket.WebSocketApp(
                        self.websocket_url,
                        header={"Authorization": auth_header},
                        on_open=self._on_open,
                        on_message=self._on_message,
                        on_error=self._on_error,
                        on_close=self._on_close
                    )
                    
                    self.ws.run_forever(ping_interval=30, ping_timeout=10)
                    
                    # If run_forever returns, connection closed
                    if not self.running:
                        break
                        
                    time.sleep(2) # Reconnect delay
                    self.log("Reconnecting...")
                    
                except Exception as e:
                    self.log(f"WebSocket run error: {e}")
                    time.sleep(5)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the WebSocket"""
        self.running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=2)
