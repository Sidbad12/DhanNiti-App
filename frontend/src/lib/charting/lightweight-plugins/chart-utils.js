
// @ts-nocheck

// Chart Utility Functions for rendering candlestick charts efficiently
// Includes position calculations, OHLC data validation, and optimized candle drawing


// Cache for position calculations to improve performance
const positionCache = new Map();


/**
 * Calculate the pixel position and length for a line, with caching.
 * @param {number} pos - The logical position.
 * @param {number} ratio - The pixel ratio for scaling.
 * @param {number} width - The logical width.
 * @returns {{position: number, length: number}}
 */
export const positionsLine = (pos, ratio, width = 1) => {
    const key = `${pos}-${ratio}-${width}`;
    if (positionCache.has(key)) return positionCache.get(key);
    const px = Math.round(ratio * pos);
    const w = Math.round(width * ratio);
    const result = { position: px - Math.floor(w / 2), length: w };
    // Limit cache size to 1000 entries
    if (positionCache.size < 1000) positionCache.set(key, result);
    return result;
};


/**
 * Calculate the pixel position and length for a box between two points.
 * @param {number} p1 - First logical position.
 * @param {number} p2 - Second logical position.
 * @param {number} ratio - The pixel ratio for scaling.
 * @returns {{position: number, length: number}}
 */
export const positionsBox = (p1, p2, ratio) => {
    const s1 = Math.round(ratio * p1);
    const s2 = Math.round(ratio * p2);
    return { position: Math.min(s1, s2), length: Math.abs(s2 - s1) + 1 };
};


/**
 * Validate OHLC data object for candlestick rendering.
 * @param {object} data - Data object with open, high, low, close properties.
 * @returns {boolean}
 */
export const isValidOHLCData = (data) => 
    data &&
    ['open', 'high', 'low', 'close'].every(
        key => typeof data[key] === 'number' && !Number.isNaN(data[key])
    );


/**
 * Draw a rounded candlestick on the chart canvas.
 * @param {CanvasRenderingContext2D} ctx - Canvas context.
 * @param {object} d - OHLC data object.
 * @param {number} x - Logical x position.
 * @param {number} w - Logical candle width.
 * @param {function} priceToCoordinate - Function to convert price to y coordinate.
 * @param {object} scope - Chart scope with pixel ratios.
 * @param {object} options - Drawing options (colors, border, wick, etc).
 */
export function drawRoundedCandle(ctx, d, x, w, priceToCoordinate, scope, options) {
    if (!isValidOHLCData(d)) return;

    const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;
    // Convert OHLC prices to y coordinates
    const [openY, closeY, highY, lowY] = [d.open, d.close, d.high, d.low].map(priceToCoordinate);
    if ([openY, closeY, highY, lowY].some(Number.isNaN)) return;

    const isUp = d.close >= d.open;
    // Scale x position for pixel ratio
    const scaledX = Math.round(x * h) / h;
    const xPos = positionsLine(scaledX, h, w);
    const bodyPos = positionsBox(Math.min(openY, closeY), Math.max(openY, closeY), v);

    // Draw candle body (rounded or rectangle)
    ctx.fillStyle = isUp ? options.upColor : options.downColor;
    const radius = Math.min(options.borderRadius ?? 2, Math.min(xPos.length, bodyPos.length) * 0.15);
    if (radius > 0.5 && bodyPos.length > 2) {
        ctx.beginPath();
        ctx.roundRect(xPos.position, bodyPos.position, xPos.length, bodyPos.length, radius);
        ctx.fill();
    } else {
        ctx.fillRect(xPos.position, bodyPos.position, xPos.length, bodyPos.length);
    }

    // Draw candle wicks (top and bottom)
    if (options.wickVisible) {
        ctx.fillStyle = isUp ? options.wickUpColor : options.wickDownColor;
        const wickPos = positionsLine(scaledX, h, 1);
        // Top wick
        if (highY < Math.min(openY, closeY)) {
            const upWick = positionsBox(highY, Math.min(openY, closeY), v);
            ctx.fillRect(wickPos.position, upWick.position, wickPos.length, upWick.length);
        }
        // Bottom wick
        if (Math.max(openY, closeY) < lowY) {
            const lowWick = positionsBox(Math.max(openY, closeY), lowY, v);
            ctx.fillRect(wickPos.position, lowWick.position, wickPos.length, lowWick.length);
        }
    }

    // Draw candle border if enabled and body is visible
    if (options.borderVisible && Math.abs(openY - closeY) > 2) {
        ctx.strokeStyle = isUp ? options.borderUpColor : options.borderDownColor;
        ctx.lineWidth = options.borderWidth ?? 0.5;
        if (radius > 0.5 && bodyPos.length > 2) {
            ctx.beginPath();
            ctx.roundRect(xPos.position + 0.5, bodyPos.position + 0.5, xPos.length - 1, bodyPos.length - 1, radius);
            ctx.stroke();
        } else {
            ctx.strokeRect(xPos.position + 0.5, bodyPos.position + 0.5, xPos.length - 1, bodyPos.length - 1);
        }
    }
}
