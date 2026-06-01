import { io, Socket } from 'socket.io-client';

const SOCKET_URL = process.env.NEXT_PUBLIC_CHARTING_SOCKET_URL || 'http://127.0.0.1:5000';

class ChartSocketManager {
  private socket: Socket | null = null;
  private connectionListeners: Set<(connected: boolean) => void> = new Set();
  private dataListeners: Map<string, Set<(data: any) => void>> = new Map(); // key: chartId_symbol_timeframe -> callbacks
  private activeSubscriptions: Map<string, any> = new Map(); // key: chartId_symbol -> subParams

  constructor() {
    if (typeof window !== 'undefined') {
      this.getSocket();
    }
  }

  public getSocket(): Socket {
    if (!this.socket) {
      this.socket = io(SOCKET_URL, {
        transports: ['websocket', 'polling'],
        autoConnect: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20000,
      });

      this.socket.on('connect', () => {
        console.log('[Socket] Connected to charting server');
        this.notifyConnection(true);
        this.resubscribeAll();
      });

      this.socket.on('disconnect', () => {
        console.log('[Socket] Disconnected from charting server');
        this.notifyConnection(false);
      });

      this.socket.on('connect_error', (error) => {
        console.error('[Socket] Connection error:', error);
        this.notifyConnection(false);
      });

      this.socket.on('live_data_update', (msg: any) => {
        const symbol = msg.symbol;
        this.triggerDataUpdate(symbol, msg);
      });
    }
    return this.socket;
  }

  public onConnectionChange(callback: (connected: boolean) => void): () => void {
    this.connectionListeners.add(callback);
    if (this.socket) {
      callback(this.socket.connected);
    } else {
      callback(false);
    }
    return () => {
      this.connectionListeners.delete(callback);
    };
  }

  private notifyConnection(connected: boolean) {
    this.connectionListeners.forEach(cb => cb(connected));
  }

  public subscribe(
    symbol: string,
    chartId: string,
    timeframe: string,
    bucketSize: number,
    multiplier: number,
    histSeed: any,
    onData: (data: any) => void
  ): () => void {
    const socket = this.getSocket();
    
    const listenerKey = `${chartId}_${symbol}_${timeframe}`;
    if (!this.dataListeners.has(listenerKey)) {
      this.dataListeners.set(listenerKey, new Set());
    }
    this.dataListeners.get(listenerKey)!.add(onData);

    const subParams = { symbol, chart_id: chartId, timeframe, bucket_size: bucketSize, multiplier, hist_seed: histSeed };
    const roomKey = `${chartId}_${symbol}`;
    this.activeSubscriptions.set(roomKey, subParams);

    socket.emit('subscribe_symbol', subParams);
    console.log(`[Socket] Subscribing to ${symbol} for chart ${chartId}`);

    return () => {
      const listeners = this.dataListeners.get(listenerKey);
      if (listeners) {
        listeners.delete(onData);
        if (listeners.size === 0) {
          this.dataListeners.delete(listenerKey);
        }
      }

      const hasOtherListeners = Array.from(this.dataListeners.keys()).some(k => k.startsWith(`${chartId}_${symbol}`));
      if (!hasOtherListeners) {
        socket.emit('unsubscribe_symbol', { symbol, chart_id: chartId });
        this.activeSubscriptions.delete(roomKey);
        console.log(`[Socket] Unsubscribed from ${symbol} for chart ${chartId}`);
      }
    };
  }

  private triggerDataUpdate(symbol: string, msg: any) {
    this.dataListeners.forEach((callbacks, key) => {
      const parts = key.split('_');
      const keySymbol = parts[1];
      const keyTimeframe = parts[2];
      
      if (keySymbol === symbol && (!msg.timeframe || msg.timeframe === keyTimeframe)) {
        callbacks.forEach(cb => cb(msg.data));
      }
    });
  }

  private resubscribeAll() {
    if (!this.socket) return;
    console.log('[Socket] Resubscribing all active symbols...');
    this.activeSubscriptions.forEach((params) => {
      this.socket!.emit('subscribe_symbol', params);
    });
  }
}

export const socketManager = new ChartSocketManager();
