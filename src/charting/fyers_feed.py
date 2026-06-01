import logging
from .auth import FyersAuth
from .versova import FyersVersovaEngine

logger = logging.getLogger(__name__)

class FyersFeed:
    """
    Interface for the real Fyers Versova L2 live depth WebSocket stream.
    Instantiates FyersVersovaEngine when credentials are valid.
    """
    def __init__(self, symbols, on_message_callback=None, log_callback=None):
        self.symbols = symbols
        self.on_message_callback = on_message_callback
        self.log_callback = log_callback or logger.info
        self.engine = None
        self.running = False
        
    def start(self):
        try:
            client_id, access_token = FyersAuth.get_fyers_credentials()
            if not client_id or not access_token:
                self.log_callback("Fyers credentials not found. Live feed will not start.")
                return False
                
            self.engine = FyersVersovaEngine(
                auth_token=access_token,
                api_key=client_id,
                symbols=self.symbols,
                on_message_callback=self.on_message_callback,
                log_callback=self.log_callback
            )
            self.engine.start()
            self.running = True
            return True
        except Exception as e:
            self.log_callback(f"Failed to start Fyers live feed: {e}")
            return False
            
    def stop(self):
        self.running = False
        if self.engine:
            self.engine.stop()
            self.engine = None

    def subscribe(self, symbols):
        if self.engine:
            self.engine.subscribe(symbols)
            
    def unsubscribe(self, symbols):
        if self.engine:
            self.engine.unsubscribe(symbols)
