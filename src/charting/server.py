import os
import sys
import time
import logging
import threading
from datetime import datetime
from flask import Flask, request, jsonify, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
from dotenv import load_dotenv

# Ensure the parent directory is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.charting.auth import FyersAuth
from src.charting.versova import FyersVersovaEngine
from src.charting.processor import process_live_data, clear_processor_state
from src.charting.fyers_data import FyersDataFeed
from src.charting.fyers_sm import SymbolMaster
from src.charting.mock_feed import MockFyersFeed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AccessLogFilter(logging.Filter):
    def filter(self, record):
        return "/fyers/callback" not in record.getMessage()

logging.getLogger('werkzeug').addFilter(AccessLogFilter())

from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# Initialize Socket.IO
async_mode = os.environ.get('SOCKETIO_ASYNC_MODE', 'threading')
cors_origins_env = os.environ.get('CORS_ORIGINS', '*')
cors_allowed = '*' if cors_origins_env.strip() == '*' else [o.strip() for o in cors_origins_env.split(',') if o.strip()]
socketio = SocketIO(app, cors_allowed_origins=cors_allowed, async_mode=async_mode)

# Services
symbol_master = SymbolMaster()
auth = FyersAuth()
fyers_data_feed = FyersDataFeed()

# Global state for managing subscriptions and live data feeds
live_feeds = {}  # symbol -> {feed_instance, subscribers}
subscriber_rooms = {}  # room_id -> {symbol, timeframe, bucket_size, multiplier}
subscribed_symbols = set()  # Track all symbols currently subscribed

# Global connection for live data
global_feed = None
global_feed_thread = None

# A local Versova Engine instance to parse and format mock data book updates
local_versova_engine = FyersVersovaEngine(auth_token="mock", api_key="mock", symbols=[])

# ----------------- HTTP Routes -----------------

@app.route('/')
def index():
    return jsonify({"status": "healthy", "service": "dhanniti-charting-backend"})

# Authentication routes
@app.route('/login')
def login():
    return redirect(auth.get_auth_url())

@app.route('/auto-login')
def auto_login():
    if auth.auto_login():
        return jsonify({"success": True, "message": "Auto Login successful"})
    else:
        return jsonify({"success": False, "error": "Auto Login failed"}), 400

@app.route('/fyers/callback')
def fyers_callback():
    auth_code = request.args.get('auth_code') or request.args.get('code')
    if not auth_code:
        return "Authentication failed: No authorization code received", 400
    
    callback_auth = FyersAuth()
    if callback_auth.generate_access_token(auth_code):
        return "Authentication successful! You can close this window now."
    else:
        return "Authentication failed: Could not generate access token", 400

@app.route('/logout')
def logout():
    auth.logout()
    return jsonify({"success": True})

# API Routes
@app.route('/api/symbols', methods=['GET'])
def api_symbols():
    q = request.args.get('q', '')
    category = request.args.get('category', 'All')
    limit = int(request.args.get('limit', 50))
    return jsonify(symbol_master.unified_symbol_search(query=q, category=category, limit=limit))

@app.route('/api/watchlist', methods=['GET'])
def api_watchlist_list():
    q = request.args.get('q', '')
    limit = int(request.args.get('limit', 200))
    data = symbol_master.get_watchlist(query=q, limit=limit)
    for item in data:
        item['watchlisted'] = True
    return jsonify(data)

@app.route('/api/watchlist', methods=['POST'])
def api_watchlist_add():
    body = request.get_json(silent=True) or {}
    symbol = body.get('symbol')
    description = body.get('description', '')
    exchange = body.get('exchange', 'NSE')
    original_type = body.get('type', body.get('original_type', ''))
    if not symbol:
        return jsonify({"success": False, "error": "symbol required"}), 400
    ok = symbol_master.add_to_watchlist(symbol, description, exchange, original_type)
    return jsonify({"success": ok})

@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
def api_watchlist_remove(symbol):
    if not symbol:
        return jsonify({"success": False, "error": "symbol required"}), 400
    ok = symbol_master.remove_from_watchlist(symbol)
    return jsonify({"success": ok})

@app.route('/api/symbols/by-expiry', methods=['GET'])
def api_symbols_by_expiry():
    expiry = request.args.get('expiry', '')
    limit = int(request.args.get('limit', 50))
    if not expiry:
        return jsonify([])
    return jsonify(symbol_master.search_symbols_by_expiry(expiry, limit=limit))

@app.route('/api/symbols/refresh', methods=['POST'])
def api_symbols_refresh():
    try:
        urls = [
            "https://public.fyers.in/sym_details/NSE_CM.csv",
            "https://public.fyers.in/sym_details/NSE_FO.csv",
            "https://public.fyers.in/sym_details/NSE_CD.csv",
        ]
        symbol_master.process_all(urls)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/clear_processor_state', methods=['POST'])
def api_clear_processor_state():
    try:
        data = request.get_json() or {}
        symbol = data.get('symbol')
        timeframe = data.get('timeframe')
        bucket_size = float(data.get('bucket_size', 0.05))
        multiplier = int(data.get('multiplier', 100))
        
        if not symbol or not timeframe:
            return jsonify({'error': 'Missing symbol or timeframe'}), 400
        
        success = clear_processor_state(symbol, timeframe, bucket_size, multiplier)
        return jsonify({
            'success': success,
            'message': f'Processor state {"cleared" if success else "not found"} for {symbol}-{timeframe}',
            'symbol': symbol,
            'timeframe': timeframe
        })
    except Exception as e:
        logger.error(f"Error in /api/clear_processor_state: {e}")
        return jsonify({'error': 'Failed to clear processor state', 'details': str(e)}), 500

@app.route('/api/historical', methods=['GET'])
def api_historical():
    symbol = request.args.get('symbol')
    timeframe = request.args.get('timeframe', '5m')  # default to 5m
    bucket_size = request.args.get('bucket_size', 0.05)
    multiplier = request.args.get('multiplier', 100)
    
    if not symbol:
        return jsonify({'error': 'Missing symbol parameter'}), 400

    try:
        fresh_data_feed = FyersDataFeed()
        data = fresh_data_feed.get_historical_data(
            symbol,
            timeframe=timeframe,
            bucket_size=float(bucket_size),
            multiplier=int(multiplier)
        )
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in /api/historical: {e}")
        return jsonify({'error': 'Failed to fetch historical data', 'details': str(e)}), 500

# ----------------- Socket.IO Events -----------------

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'data': 'Connected to DhanNiti Charting Platform'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")
    cleanup_client_subscriptions(request.sid)

@socketio.on('subscribe_symbol')
def handle_subscribe_symbol(data):
    try:
        symbol = data.get('symbol')
        timeframe = data.get('timeframe', '5m')
        bucket_size = float(data.get('bucket_size', 0.05))
        multiplier = int(data.get('multiplier', 100))
        chart_id = data.get('chart_id')
        hist_seed = data.get('hist_seed')

        if not symbol or not chart_id:
            emit('error', {'message': 'Missing symbol or chart_id'})
            return

        room_id = f"{request.sid}_{chart_id}_{symbol}_{timeframe}_{bucket_size}_{multiplier}"
        join_room(room_id)

        subscriber_rooms[room_id] = {
            'symbol': symbol,
            'timeframe': timeframe,
            'bucket_size': bucket_size,
            'multiplier': multiplier,
            'chart_id': chart_id,
            'client_id': request.sid
        }

        start_live_feed(symbol, timeframe, bucket_size, multiplier, hist_seed)
        logger.info(f"Client {request.sid} subscribed to {symbol} for chart {chart_id}")
        
        emit('subscription_success', {
            'symbol': symbol,
            'chart_id': chart_id,
            'room_id': room_id
        })
    except Exception as e:
        logger.error(f"Error in subscribe_symbol: {e}")
        emit('error', {'message': str(e)})

@socketio.on('unsubscribe_symbol')
def handle_unsubscribe_symbol(data):
    try:
        symbol = data.get('symbol')
        chart_id = data.get('chart_id')

        if not symbol or not chart_id:
            emit('error', {'message': 'Missing symbol or chart_id'})
            return

        rooms_to_remove = []
        for room_id, room_data in subscriber_rooms.items():
            if (room_data['client_id'] == request.sid and
                room_data['symbol'] == symbol and
                room_data['chart_id'] == chart_id):
                rooms_to_remove.append(room_id)

        for room_id in rooms_to_remove:
            leave_room(room_id)
            del subscriber_rooms[room_id]

        stop_live_feed_if_no_subscribers(symbol)
        logger.info(f"Client {request.sid} unsubscribed from {symbol} for chart {chart_id}")
        
        emit('unsubscription_success', {
            'symbol': symbol,
            'chart_id': chart_id
        })
    except Exception as e:
        logger.error(f"Error in unsubscribe_symbol: {e}")
        emit('error', {'message': str(e)})

def cleanup_client_subscriptions(client_id):
    rooms_to_remove = []
    symbols_to_check = set()

    for room_id, room_data in subscriber_rooms.items():
        if room_data['client_id'] == client_id:
            rooms_to_remove.append(room_id)
            symbols_to_check.add(room_data['symbol'])

    for room_id in rooms_to_remove:
        del subscriber_rooms[room_id]

    for symbol in symbols_to_check:
        stop_live_feed_if_no_subscribers(symbol)

# ----------------- Feed Processing -----------------

def start_live_feed(symbol, timeframe, bucket_size, multiplier, hist_seed=None):
    global global_feed, subscribed_symbols
    subscribed_symbols.add(symbol)

    if symbol in live_feeds:
        live_feeds[symbol]['subscribers'] += 1
        return

    live_feeds[symbol] = {'subscribers': 1}

    # Seed the live processor
    if hist_seed and isinstance(hist_seed, dict):
        try:
            seed_msg = {
                'symbol': symbol,
                'ltp': float(hist_seed.get('close', 0.0) or 0.0),
                'vol_traded_today': int(hist_seed.get('volume', 0) or 0),
                'last_traded_qty': 0
            }
            process_live_data(
                seed_msg, 
                timeframe=timeframe, 
                bucket_size=bucket_size, 
                multiplier=multiplier, 
                hist_last_candle=hist_seed
            )
            logger.info(f"[SEEDED] Live aggregator for {symbol} at timeframe={timeframe} cum_delta={hist_seed.get('cum_delta', 0)}")
        except Exception as e:
            logger.error(f"[SEED FAILED] Failed to seed processor for {symbol}: {e}")
    else:
        logger.warning(f"No historical seed provided for {symbol} - starting clean")

    # Start live feed if not running
    if global_feed is None:
        try:
            start_global_feed()
        except Exception as e:
            logger.error(f"Error starting global feed: {e}")
            return

    try:
        if global_feed:
            global_feed.subscribe(symbols=[symbol])
            logger.info(f"Subscribed to {symbol} on global live feed")
    except Exception as e:
        logger.error(f"Error subscribing to {symbol}: {e}")

def start_global_feed():
    global global_feed
    is_mock = os.environ.get("MOCK_DATA") == "true" or not auth.access_token

    def global_live_data_callback(market_data):
        if not market_data:
            return
        
        # Versova engine callback format: dict of books
        if isinstance(market_data, dict):
            for symbol, book in market_data.items():
                process_book_update(book)
        else:
            logger.error(f"Unexpected live data format: {type(market_data)}")

    def mock_live_data_callback(msg):
        # Mock Feed callback format: {'type': 'live_tick', 'data': msg}
        if not msg or msg.get('type') != 'live_tick':
            return
        
        data = msg.get('data', {})
        symbol = data.get('symbol')
        if not symbol:
            return
            
        # Parse through local Versova Engine instance to construct imbalance/sentiment metrics
        local_versova_engine.update_order_book(
            ticker=symbol,
            bids=data.get('bids', []),
            asks=data.get('asks', []),
            tbq=data.get('tot_buy_qty', 0),
            tsq=data.get('tot_sell_qty', 0),
            ltp=data.get('ltp'),
            vol_traded_today=data.get('vol_traded_today'),
            timestamp=data.get('timestamp'),
            is_snapshot=True
        )
        
        book = local_versova_engine.get_full_order_book(symbol)
        if book:
            process_book_update(book)

    def process_book_update(book):
        msg_symbol = book.get('symbol')
        if not msg_symbol or msg_symbol not in subscribed_symbols:
            return

        tick_msg = {
            'symbol': msg_symbol,
            'ltp': book.get('ltp'),
            'vol_traded_today': book.get('vol_traded_today'),
            'last_traded_time': book.get('timestamp'),
            'exch_feed_time': book.get('timestamp'),
            'imbalance_50': book.get('imbalance_50'),
            'sentiment': book.get('sentiment')
        }

        # Find matching subscription rooms
        matching_rooms = [
            (room_id, room_data) for room_id, room_data in subscriber_rooms.items()
            if room_data['symbol'] == msg_symbol
        ]

        for room_id, room_data in matching_rooms:
            try:
                room_timeframe = room_data['timeframe']
                room_bucket_size = room_data['bucket_size']
                room_multiplier = room_data['multiplier']

                processed_data = process_live_data(
                    tick_msg,
                    timeframe=room_timeframe,
                    bucket_size=room_bucket_size,
                    multiplier=room_multiplier
                )

                if processed_data:
                    # Enriched metadata for charts
                    processed_data['imbalance_50'] = book.get('imbalance_50')
                    processed_data['sentiment'] = book.get('sentiment')
                    processed_data['bids'] = book.get('bids', [])[:50]
                    processed_data['asks'] = book.get('asks', [])[:50]
                    processed_data['tbq'] = book.get('tbq', 0)
                    processed_data['tsq'] = book.get('tsq', 0)
                    
                    socketio.emit('live_data_update', {
                        'symbol': msg_symbol,
                        'chart_id': room_data['chart_id'],
                        'data': processed_data,
                        'timeframe': room_timeframe,
                        'timestamp': time.time()
                    }, room=room_id)
            except Exception as e:
                logger.error(f"Error processing tick for room {room_id}: {e}")

    if is_mock:
        logger.info("[STARTING MOCK FEED SERVICE]")
        feed = MockFyersFeed(symbols=list(subscribed_symbols), on_message_callback=mock_live_data_callback)
        global_feed = feed
        feed.start()
    else:
        logger.info("[STARTING REAL FYERS LIVE FEED]")
        client_id, access_token = FyersAuth.get_fyers_credentials()
        engine = FyersVersovaEngine(
            auth_token=access_token,
            api_key=client_id,
            symbols=list(subscribed_symbols),
            on_message_callback=global_live_data_callback,
            log_callback=logger.info
        )
        global_feed = engine
        engine.start()

def stop_live_feed_if_no_subscribers(symbol):
    global global_feed, subscribed_symbols
    if symbol not in live_feeds:
        return

    has_subscribers = any(
        room_data['symbol'] == symbol
        for room_data in subscriber_rooms.values()
    )

    if not has_subscribers:
        subscribed_symbols.discard(symbol)
        try:
            if global_feed:
                global_feed.unsubscribe(symbols=[symbol])
        except Exception as e:
            logger.error(f"Error unsubscribing from {symbol}: {e}")

        if symbol in live_feeds:
            del live_feeds[symbol]
        
        logger.info(f"Stopped live feed for {symbol} - no active subscribers")

        if not subscribed_symbols and global_feed:
            try:
                global_feed.stop()
                global_feed = None
                logger.info("Stopped global live feed - no active symbols remaining")
            except Exception as e:
                logger.error(f"Error stopping global feed: {e}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run DhanNiti Charting Backend')
    parser.add_argument('--port', type=int, default=int(os.environ.get('APP_PORT', 5000)), help='Port to run app on')
    args = parser.parse_args()
    
    # Enable mock data by default if environment says so or if credentials are not present
    if not os.environ.get("MOCK_DATA"):
        os.environ["MOCK_DATA"] = "true"
        
    debug = os.environ.get('FLASK_ENV', 'development') != 'production'
    host = os.environ.get('APP_HOST', '0.0.0.0')
    
    logger.info(f"Starting DhanNiti Charting Backend on {host}:{args.port} (async_mode={async_mode}, mock_mode={os.environ.get('MOCK_DATA')})")
    socketio.run(app, debug=debug, host=host, port=args.port, allow_unsafe_werkzeug=True)
