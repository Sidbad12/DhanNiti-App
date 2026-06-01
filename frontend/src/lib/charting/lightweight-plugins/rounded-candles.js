// @ts-nocheck
// --- Optimized Rounded Candlestick Series Plugin ---
import { drawRoundedCandle, isValidOHLCData } from './chart-utils.js';

// High-performance candlestick renderer
class RoundedCandlestickRenderer {
    constructor() {
        this._data = null;
        this._options = null;
    }

    draw(target, priceToCoordinate) {
        target.useBitmapCoordinateSpace(scope => this._drawImpl(scope, priceToCoordinate));
    }

    update(data, options) {
        this._data = data;
        this._options = options;
    }

    _drawImpl(scope, priceToCoordinate) {
        const { bars, visibleRange, barSpacing } = this._data || {};
        if (!bars?.length || !visibleRange) return;
        
        const ctx = scope.context;
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        
        try {
            const candleWidth = Math.max(1, Math.min(barSpacing * 0.8, 20));
            
            for (let i = visibleRange.from; i < visibleRange.to; ++i) {
                const bar = bars[i];
                if (bar?.originalData && isValidOHLCData(bar.originalData)) {
                    drawRoundedCandle(ctx, bar.originalData, bar.x, candleWidth, priceToCoordinate, scope, this._options);
                }
            }
        } finally {
            ctx.restore();
        }
    }
}

// Optimized series object with default options and instance creation
const DEFAULT_OPTIONS = {
    upColor: '#089981', downColor: '#F23645', borderUpColor: '#089981', borderDownColor: '#F23645',
    wickUpColor: '#089981', wickDownColor: '#F23645', borderVisible: true, wickVisible: true,
    borderRadius: 2, borderWidth: 1, visible: true
};

export const RoundedCandlestickSeries = {
    // Create a new instance for each chart instead of sharing
    create() {
        return Object.create(this, {
            _renderer: { value: null, writable: true },
            _options: { value: null, writable: true }
        });
    },

    renderer() {
        return this._renderer ??= new RoundedCandlestickRenderer();
    },

    update(data, options) {
        this._options = { ...DEFAULT_OPTIONS, ...this._options, ...options };
        this.renderer().update(data, this._options);
    },

    priceValueBuilder(row) {
        return isValidOHLCData(row) ? [row.open, row.high, row.low, row.close] : [0, 0, 0, 0];
    },

    isWhitespace(row) {
        return !isValidOHLCData(row);
    },

    defaultOptions() {
        return DEFAULT_OPTIONS;
    },

    applyOptions(options) {
        this._options = { ...this._options || DEFAULT_OPTIONS, ...options };
        return this;
    },

    destroy() {
        this._renderer = null;
        this._options = null;
    }
};
